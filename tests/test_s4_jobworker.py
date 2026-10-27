import importlib.util
import pathlib
import queue
import socketserver
import threading
import time
import urllib.request

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER_PATH = ROOT / "deploy/lab/workloads/jobworker.py"
spec = importlib.util.spec_from_file_location("jobworker", WORKER_PATH)
jobworker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jobworker)


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
