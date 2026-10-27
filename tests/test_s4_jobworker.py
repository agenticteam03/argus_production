import importlib.util
import pathlib
import queue
import socketserver
import threading
import time
import urllib.error
import urllib.request

import pytest
import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER_PATH = ROOT / "deploy/lab/workloads/jobworker.py"
spec = importlib.util.spec_from_file_location("jobworker", WORKER_PATH)
jobworker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jobworker)
producer_spec = importlib.util.spec_from_file_location("jobproducer", ROOT / "deploy/lab/workloads/jobproducer.py")
jobproducer = importlib.util.module_from_spec(producer_spec)
producer_spec.loader.exec_module(jobproducer)


class FakeRedis:
    def __init__(self):
        self.items = queue.Queue()

    def blpop(self, key, timeout=1):
        assert key == "lab:jobs"
        try:
            return key, self.items.get(timeout=timeout)
        except queue.Empty:
            return None

    def llen(self, key):
        assert key == "lab:jobs"
        return self.items.qsize()

    def rpush(self, key, value):
        assert key == "lab:jobs"
        self.items.put(value)


class RedisRespHandler(socketserver.StreamRequestHandler):
    def handle(self):
        count = int(self.rfile.readline()[1:])
        command = []
        for _ in range(count):
            size = int(self.rfile.readline()[1:])
            command.append(self.rfile.read(size).decode())
            self.rfile.read(2)
        if command[0] == "BLPOP":
            self.wfile.write(b"*2\r\n$8\r\nlab:jobs\r\n$3\r\njob\r\n")
        else:
            self.wfile.write(b":1\r\n")


def test_redis_list_parses_real_resp_array_and_integer():
    server = socketserver.TCPServer(("127.0.0.1", 0), RedisRespHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        redis = jobworker.RedisList("127.0.0.1", server.server_address[1])
        assert redis.blpop("lab:jobs", timeout=1) == ("lab:jobs", "job")
        assert redis.llen("lab:jobs") == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_worker_freezes_queue_but_stays_healthy_and_drains_after_unfreeze():
    redis = FakeRedis()
    state = jobworker.WorkerState("missing-freeze-flag")
    stop = threading.Event()
    thread = threading.Thread(target=jobworker.worker_loop, args=(redis, state, stop), daemon=True)
    thread.start()
    redis.rpush("lab:jobs", "first")
    deadline = time.monotonic() + 2
    while state.processed < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert state.processed == 1

    state.frozen = True
    for value in range(3):
        redis.rpush("lab:jobs", str(value))
    time.sleep(0.15)
    assert state.processed == 1
    assert redis.llen("lab:jobs") == 3

    server = jobworker.ThreadingHTTPServer(("127.0.0.1", 0), jobworker.make_handler(redis, state))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/health") as response:
            assert response.status == 200
        state.frozen = False
        deadline = time.monotonic() + 2
        while (state.processed < 4 or redis.llen("lab:jobs")) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert state.processed == 4
        assert redis.llen("lab:jobs") == 0
    finally:
        server.shutdown()
        stop.set()
        thread.join(timeout=2)
        server.server_close()


def test_compose_declares_sc10_job_containers():
    compose = yaml.safe_load((ROOT / "deploy/lab/compose.lab.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["argus-lab-jobworker"]["profiles"] == ["sc10"]
    assert services["argus-lab-jobproducer"]["profiles"] == ["sc10"]
    assert services["argus-lab-jobworker"]["container_name"] == "argus-lab-jobworker"
    assert services["argus-lab-jobproducer"]["container_name"] == "argus-lab-jobproducer"


class DropThenRecoverHandler(socketserver.StreamRequestHandler):
    connections = 0

    def handle(self):
        type(self).connections += 1
        if type(self).connections == 1:
            return
        count = int(self.rfile.readline()[1:])
        command = []
        for _ in range(count):
            size = int(self.rfile.readline()[1:])
            command.append(self.rfile.read(size).decode())
            self.rfile.read(2)
        if command[0] == "BLPOP":
            if type(self).connections == 2:
                self.wfile.write(b"*2\r\n$8\r\nlab:jobs\r\n$3\r\njob\r\n")
            else:
                self.wfile.write(b"*-1\r\n")


def test_worker_survives_redis_connection_drop_and_resumes():
    DropThenRecoverHandler.connections = 0
    server = socketserver.TCPServer(("127.0.0.1", 0), DropThenRecoverHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state = jobworker.WorkerState("missing-freeze-flag")
    stop = threading.Event()
    redis = jobworker.RedisList("127.0.0.1", server.server_address[1])
    worker = threading.Thread(target=jobworker.worker_loop,
                              args=(redis, state, stop), kwargs={"error_wait": 0.01}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while state.processed < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert state.processed == 1
        assert DropThenRecoverHandler.connections >= 2
    finally:
        stop.set()
        worker.join(timeout=2)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_producer_retries_redis_errors_and_resumes(monkeypatch):
    stop = threading.Event()
    attempts = []

    def rpush(_host, _key, _value):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("Redis unavailable")
        stop.set()

    monkeypatch.setattr(jobproducer, "rpush", rpush)
    jobproducer.producer_loop("cache", stop, retry_wait=0.001, interval=0.001)
    assert len(attempts) == 2


def test_metrics_degrade_when_redis_llen_fails():
    class BrokenRedis:
        def llen(self, _key):
            raise RuntimeError("Redis unavailable")

    state = jobworker.WorkerState("missing-freeze-flag")
    server = jobworker.ThreadingHTTPServer(("127.0.0.1", 0), jobworker.make_handler(BrokenRedis(), state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/metrics") as response:
            body = response.read().decode()
            assert response.status == 200
            assert "argus_lab_queue_depth NaN" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_fault_endpoints_require_fault_enable(monkeypatch):
    monkeypatch.delenv("FAULT_ENABLE", raising=False)
    state = jobworker.WorkerState("missing-freeze-flag")
    server = jobworker.ThreadingHTTPServer(("127.0.0.1", 0), jobworker.make_handler(FakeRedis(), state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/fault/freeze")
        assert exc.value.code == 404
        monkeypatch.setenv("FAULT_ENABLE", "1")
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/fault/freeze") as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_compose_passes_fault_enable_to_api_and_worker():
    compose = yaml.safe_load((ROOT / "deploy/lab/compose.lab.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["argus-lab-api"]["environment"]["FAULT_ENABLE"] == "${FAULT_ENABLE:-0}"
    assert services["argus-lab-jobworker"]["environment"]["FAULT_ENABLE"] == "${FAULT_ENABLE:-0}"
