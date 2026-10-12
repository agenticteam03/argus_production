"""T-0019 batch 2: the host-probe's diagnosis verbs (ARCHITECTURE §4.6) and their Level 2 capabilities (§12.2).

load, io, top processes (CPU and memory), socket summary, directory sizes and kernel OOM records. Every verb reads
what `argus-v18-host-probe` already mounts read-only (/proc → /host/proc, / → /rootfs): no new mount, no privilege, no
shell, never a process's command line or environment, never a network address. A missing source is unknown, not zero.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from argus.application.invoke_capability import InvocationContext
from argus.capabilities.spec import ExecutorError
from test_core import FakeTargetAgent, incident, make_app  # noqa: F401  (make_app is a fixture)
from test_db_probe import _load

ROOT = Path(__file__).resolve().parents[1]
HOST = "vm-166/host:vm-166"
CID = "1a2b3c4d5e6f" + "0" * 52                                  # a Docker container id (64 hex)
FILL = "/srv/argus-lab-fill"


# --- a fake host: /proc and / as the probe sees them ----------------------------------------------
def _stat(pid: int, comm: str, state: str = "S", ppid: int = 1, ticks: int = 0, rss_pages: int = 0) -> str:
    rest = [state, str(ppid)] + ["0"] * 9 + [str(ticks), "0"] + ["0"] * 8 + [str(rss_pages)] + ["0"] * 20
    return f"{pid} ({comm}) " + " ".join(rest) + "\n"


class FakeHost:
    def __init__(self, tmp_path: Path):
        self.proc, self.rootfs = tmp_path / "proc", tmp_path / "rootfs"
        self.proc.mkdir()
        (self.rootfs / "sys" / "block").mkdir(parents=True)
        (self.rootfs / "var" / "log").mkdir(parents=True)
        self.write("loadavg", "0.52 0.40 0.31 3/412 9999\n")
        self.write("stat", "cpu  1 1 1 1 1\ncpu0 1 1 1 1 1\ncpu1 1 1 1 1 1\n")
        self.write("meminfo", "MemTotal: 5917000 kB\nMemAvailable: 4000000 kB\n")
        self.write("vmstat", "nr_free_pages 1\noom_kill 18567\n")

    def write(self, rel: str, text: str) -> Path:
        p = self.proc / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def process(self, pid: int, comm: str, cgroup: str = "0::/init.scope", **kw) -> None:
        self.write(f"{pid}/stat", _stat(pid, comm, **kw))
        self.write(f"{pid}/cgroup", cgroup + "\n")
        self.write(f"{pid}/cmdline", "secret-tool\0--password=hunter2\0")
        self.write(f"{pid}/environ", "DB_PASSWORD=hunter2\0")

    def kern_log(self, lines: list[str], name: str = "kern.log") -> Path:
        p = self.rootfs / "var" / "log" / name
        p.write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")
        return p


@pytest.fixture
def host(tmp_path):
    return FakeHost(tmp_path)


def _probe(host: FakeHost, monkeypatch, mounts=("/", FILL)):
    cfg = host.proc.parent / "target.json"
    cfg.write_text(json.dumps({"host": "vm-166", "containers": [], "mounts": list(mounts)}), encoding="utf-8")
    (host.proc.parent / "host_probe_token").write_text("t0ken", encoding="utf-8")
    for k, v in {"ROLE": "host_probe", "TA_CONFIG": str(cfg), "TA_SECRETS": str(host.proc.parent),
                 "TA_PROC": str(host.proc), "TA_ROOTFS": str(host.rootfs)}.items():
        monkeypatch.setenv(k, v)
    svc = _load("ta_service_host", ROOT / "services" / "target" / "service.py")
    svc.PAGE_BYTES, svc.CLK_TCK = 4096, 100                                     # the fake host's, on any machine
    return svc


def _err(svc, parts, q=None) -> int:
    with pytest.raises(svc.Err) as e:
        svc.host_probe(parts, q or {})
    return e.value.code


# --- load ---------------------------------------------------------------------------------------------
def test_load_reports_three_averages_runnable_threads_and_pressure(host, monkeypatch):
    host.write("pressure/cpu", "some avg10=12.50 avg60=8.00 avg300=2.00 total=1\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    host.write("pressure/io", "some avg10=1.00 avg60=0.50 avg300=0.10 total=1\nfull avg10=0.50 avg60=0.20 avg300=0.05 total=1\n")
    host.write("pressure/memory", "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    d = _probe(host, monkeypatch).host_probe(["load"], {})
    assert (d["load1"], d["load5"], d["load15"], d["runnable"], d["threads"], d["cpus"]) == (0.52, 0.40, 0.31, 3, 412, 2)
    assert d["pressure"]["cpu"]["some"] == {"avg10": 12.5, "avg60": 8.0, "avg300": 2.0}
    assert d["pressure"]["io"]["full"]["avg10"] == 0.5


def test_load_without_pressure_files_says_unknown_not_zero(host, monkeypatch):
    d = _probe(host, monkeypatch).host_probe(["load"], {})
    assert d["pressure"] == {"cpu": None, "memory": None, "io": None}


# --- io -----------------------------------------------------------------------------------------------
def _diskstats(sda: tuple[int, int, int, int, int]) -> str:
    r, sr, w, sw, ticks = sda
    line = lambda name, a, b, c, d, t: f"   8       0 {name} {a} 0 {b} 0 {c} 0 {d} 0 0 {t} 0 0 0 0 0 0 0\n"  # noqa: E731
    return (line("sda", r, sr, w, sw, ticks) + line("sda1", r, sr, w, sw, ticks)
            + line("loop0", 99, 99, 99, 99, 99))


def test_io_rates_cover_whole_devices_only(host, monkeypatch):
    for dev in ("sda", "loop0"):
        (host.rootfs / "sys" / "block" / dev).mkdir()
    host.write("diskstats", _diskstats((100, 2000, 50, 8000, 1000)))
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.time, "sleep", lambda s: host.write("diskstats", _diskstats((110, 4048, 70, 16192, 1500))))
    d = svc.host_probe(["io"], {})
    assert [x["device"] for x in d["devices"]] == ["sda"]                       # no partition, no loop device
    sda = d["devices"][0]
    assert (sda["reads_s"], sda["writes_s"]) == (10.0, 20.0)                     # over the 1 s sample
    assert (sda["read_kib_s"], sda["write_kib_s"]) == (1024.0, 4096.0)           # 512-byte sectors
    assert sda["busy_percent"] == 50.0                                           # 500 ms of io time in 1000 ms
    assert d["interval_s"] == 1.0 and "pressure" in d


# --- top processes ------------------------------------------------------------------------------------
def _three_processes(host, ticks=(0, 0, 0)):
    host.process(4242, "stress", cgroup=f"0::/../docker-{CID}.scope", ticks=ticks[0], rss_pages=2560)
    host.process(77, "dockerd", cgroup="0::/system.slice/docker.service", ticks=ticks[1], rss_pages=25600)
    host.process(12, "kworker/0:1", ppid=2, ticks=ticks[2])


def test_top_cpu_ranks_by_cpu_and_names_the_container_by_id(host, monkeypatch):
    _three_processes(host)
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.time, "sleep", lambda s: _three_processes(host, ticks=(49, 1, 0)))
    d = svc.host_probe(["processes"], {"by": ["cpu"], "n": ["2"]})
    top = d["processes"]
    assert [p["pid"] for p in top] == [4242, 77] and d["by"] == "cpu"
    assert top[0]["cpu_percent"] == 98.0                                         # 49 ticks of 100/s in 0.5 s
    assert top[0]["container_id"] == CID[:12] and top[1]["container_id"] is None
    assert top[0]["command"] == "stress" and top[0]["rss_mib"] == 10.0


def test_top_memory_ranks_by_rss_in_one_read(host, monkeypatch):
    _three_processes(host)
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.time, "sleep", lambda s: pytest.fail("memory needs no second sample"))
    d = svc.host_probe(["processes"], {"by": ["memory"]})
    assert [p["pid"] for p in d["processes"]][:2] == [77, 4242]
    assert d["processes"][0]["rss_mib"] == 100.0 and "cpu_percent" not in d["processes"][0]


def test_top_processes_never_read_a_command_line_or_an_environment(host, monkeypatch):
    _three_processes(host)
    svc = _probe(host, monkeypatch)
    opened: list[str] = []
    real_open = open
    monkeypatch.setattr(svc, "open", lambda p, *a, **k: (opened.append(str(p)), real_open(p, *a, **k))[1], raising=False)
    monkeypatch.setattr(svc.time, "sleep", lambda s: None)
    for by in ("cpu", "memory"):
        d = svc.host_probe(["processes"], {"by": [by]})
        assert "hunter2" not in json.dumps(d) and "secret-tool" not in json.dumps(d)
    assert opened and not [p for p in opened if p.endswith(("cmdline", "environ"))]


def test_top_processes_refuse_another_order_and_bound_n(host, monkeypatch):
    _three_processes(host)
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.time, "sleep", lambda s: None)
    assert _err(svc, ["processes"], {"by": ["disk"]}) == 400
    assert len(svc.host_probe(["processes"], {"by": ["memory"], "n": ["500"]})["processes"]) == 3   # n ≤ 10
    assert svc.PROCESS_MAX_N == 10


# --- sockets ------------------------------------------------------------------------------------------
TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:4952 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 1 0 100 0 0 10 0
   1: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 2 1 0 100 0 0 10 0
   2: 0A00000F:0016 0A000063:D431 01 00000000:00000000 02:00000000 00000000     0        0 3 1 0 20 4 30 10 -1
   3: 0A00000F:0016 0A000064:D432 06 00000000:00000000 03:00000000 00000000     0        0 0 3 0 0 0 0 0 0
"""


def test_sockets_count_the_host_namespace_by_state_without_addresses(host, monkeypatch):
    host.write("1/net/tcp", TCP)
    host.write("1/net/tcp6", TCP.splitlines()[0] + "\n")
    host.write("1/net/sockstat", "sockets: used 322\nTCP: inuse 23 orphan 1 tw 2 alloc 56 mem 224\nUDP: inuse 3 mem 0\n")
    host.write("net/tcp", TCP.splitlines()[0] + "\n")                           # the probe's own namespace: empty
    d = _probe(host, monkeypatch).host_probe(["sockets"], {})
    assert d["tcp_by_state"] == {"listen": 2, "established": 1, "time_wait": 1}
    assert d["listening_ports"] == [22, 18770] and d["sockstat"]["TCP"]["tw"] == 2
    assert d["namespace"] == "host (pid 1)"
    text = json.dumps(d)
    assert "0A00000F" not in text and "10.0.0" not in text and "0100007F" not in text


def test_sockets_unreadable_host_namespace_is_an_error_not_zero(host, monkeypatch):
    assert _err(_probe(host, monkeypatch), ["sockets"]) == 503


# --- directory sizes ----------------------------------------------------------------------------------
def _fill(host) -> Path:
    base = host.rootfs / FILL.lstrip("/")
    (base / "big").mkdir(parents=True)
    (base / "big" / "f1").write_bytes(b"x" * 256 * 1024)
    (base / "big" / "f2").write_bytes(b"x" * 256 * 1024)
    (base / "small").mkdir()
    (base / "small" / "f").write_bytes(b"x" * 8 * 1024)
    (base / "file.log").write_bytes(b"x" * 64 * 1024)
    return base


def test_directory_sizes_rank_the_children_of_a_declared_mount(host, monkeypatch):
    _fill(host)
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.os.path, "ismount", lambda p: True)
    d = svc.host_probe(["directory_sizes"], {"path": [FILL]})
    assert [c["name"] for c in d["children"]] == ["big/", "file.log", "small/"]
    assert d["complete"] is True and d["entries_read"] >= 6 and d["path"] == FILL
    assert d["children"][0]["mib"] >= 0.5 and d["children"][0]["complete"] is True


def test_directory_sizes_refuse_a_path_that_is_not_a_declared_mount(host, monkeypatch):
    _fill(host)
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.os.path, "ismount", lambda p: True)
    for path in ("/etc", FILL + "/big", FILL + "/../..", "/root"):
        assert _err(svc, ["directory_sizes"], {"path": [path]}) == 400, path
    monkeypatch.setattr(svc.os.path, "ismount", lambda p: False)
    assert _err(svc, ["directory_sizes"], {"path": [FILL]}) == 409             # not mounted: unknown, not the root disk


def test_directory_sizes_stop_at_their_budget_and_say_so(host, monkeypatch):
    _fill(host)
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.os.path, "ismount", lambda p: True)
    monkeypatch.setattr(svc, "DIR_MAX_ENTRIES", 3)
    d = svc.host_probe(["directory_sizes"], {"path": [FILL]})
    assert d["complete"] is False and d["entries_read"] == 3
    assert any(c["complete"] is False for c in d["children"]) or len(d["children"]) < 3


def test_directory_sizes_share_the_budget_so_every_child_is_measured(host, monkeypatch):
    """Step 03 on vm-095: walking `/` in name order, `usr/` used the whole budget and `var/` (logs, Docker) was never
    read. Each child now gets a share of what is left, so a late child is measured, at least partly."""
    base = host.rootfs / FILL.lstrip("/")
    (base / "a_many").mkdir(parents=True)
    for i in range(30):
        (base / "a_many" / f"f{i}").write_bytes(b"x")
    (base / "z_big").mkdir()
    (base / "z_big" / "f").write_bytes(b"x" * 512 * 1024)
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.os.path, "ismount", lambda p: True)
    monkeypatch.setattr(svc, "DIR_MAX_ENTRIES", 10)
    d = svc.host_probe(["directory_sizes"], {"path": [FILL]})
    names = [c["name"] for c in d["children"]]
    assert names[0] == "z_big/" and "a_many/" in names and d["complete"] is False
    assert next(c for c in d["children"] if c["name"] == "a_many/")["complete"] is False


def test_directory_sizes_do_not_follow_symlinks(host, monkeypatch, tmp_path):
    base = _fill(host)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "huge").write_bytes(b"x" * 2 * 1024 * 1024)
    try:
        os.symlink(outside, base / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available here")
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc.os.path, "ismount", lambda p: True)
    d = svc.host_probe(["directory_sizes"], {"path": [FILL]})
    link = next(c for c in d["children"] if c["name"].startswith("link"))
    assert link["mib"] < 0.1 and d["children"][0]["name"] == "big/"


# --- kernel OOM records -------------------------------------------------------------------------------
def _syslog_ts(t: datetime) -> str:
    return f"{t:%b} {t.day:>2} {t:%H:%M:%S}"


def _oom(t: datetime, pid: int, comm: str, cid: str | None = CID, rss_kb: int = 65024) -> list[str]:
    cpuset = f"docker-{cid}.scope" if cid else "/"
    constraint = "CONSTRAINT_MEMCG" if cid else "CONSTRAINT_NONE"
    memcg = f"/system.slice/docker-{cid}.scope" if cid else "/"
    ts = _syslog_ts(t)
    return [f"{ts} argus-vm166 kernel: [468000.1] {comm} invoked oom-killer: gfp_mask=0xcc0(GFP_KERNEL), order=0",
            f"{ts} argus-vm166 kernel: [468000.2] oom-kill:constraint={constraint},nodemask=(null),cpuset={cpuset},"
            f"mems_allowed=0,oom_memcg={memcg},task_memcg={memcg},task={comm},pid={pid},uid=0",
            f"{ts} argus-vm166 kernel: [468000.3] Memory cgroup out of memory: Killed process {pid} ({comm}) "
            f"total-vm:76704kB, anon-rss:{rss_kb}kB, file-rss:5376kB, shmem-rss:0kB, UID:0 pgtables:196kB oom_score_adj:0"]


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def test_kernel_oom_records_in_the_window_with_their_container(host, monkeypatch):
    host.kern_log(_oom(NOW - timedelta(minutes=120), 100, "old") + ["x kernel: noise"]
                  + _oom(NOW - timedelta(minutes=10), 2560725, "python")
                  + _oom(NOW - timedelta(minutes=5), 31, "java", cid=None, rss_kb=2097152))
    d = _probe(host, monkeypatch).host_probe(["oom"], {"minutes": ["60"]})
    assert d["source"] == "kern.log" and d["complete"] is True and d["records_total"] == 2
    latest, first = d["records"][-1], d["records"][0]
    assert (first["pid"], first["command"], first["scope"], first["container_id"], first["anon_rss_mib"]) == \
        (2560725, "python", "memcg", CID[:12], 63.5)
    assert (latest["scope"], latest["container_id"], latest["anon_rss_mib"]) == ("host", None, 2048.0)
    assert d["by_container"] == [{"container_id": CID[:12], "count": 1}, {"container_id": None, "count": 1}]
    assert d["oom_kill_since_boot"] == 18567 and d["window_minutes"] == 60


def test_kernel_oom_records_read_the_rotated_file_when_the_current_one_starts_later(host, monkeypatch):
    host.kern_log(_oom(NOW - timedelta(minutes=50), 7, "rotated"), name="kern.log.1")
    host.kern_log([f"{_syslog_ts(NOW - timedelta(minutes=20))} argus-vm166 kernel: [1.0] eth0: link up"]
                  + _oom(NOW - timedelta(minutes=2), 8, "current"))
    d = _probe(host, monkeypatch).host_probe(["oom"], {"minutes": ["60"]})
    assert [r["command"] for r in d["records"]] == ["rotated", "current"] and d["complete"] is True


def test_kernel_oom_records_read_a_bounded_tail_and_say_when_it_is_partial(host, monkeypatch):
    lines = []
    for i in range(40):
        lines += _oom(NOW - timedelta(minutes=40 - i), 1000 + i, "leaky")
    host.kern_log(lines)
    svc = _probe(host, monkeypatch)
    monkeypatch.setattr(svc, "OOM_MAX_BYTES", 2048)
    d = svc.host_probe(["oom"], {"minutes": ["60"]})
    assert d["complete"] is False and 0 < d["records_total"] < 40
    assert len(d["records"]) <= svc.OOM_MAX_RECORDS == 10


def test_kernel_oom_records_stream_the_log_instead_of_holding_it(host, monkeypatch):
    """Step 03 on vm-166: the 64 MiB probe was OOM-killed while answering; `/oom?minutes=1440` alone added 16 MiB
    (4 MiB of log held as text and parsed lines). The tail is now read line by line, keeping only OOM lines."""
    import tracemalloc
    noise = f"{_syslog_ts(NOW - timedelta(minutes=30))} argus-vm166 kernel: [1.0] " + "x" * 180
    host.kern_log([noise] * 20000 + _oom(NOW - timedelta(minutes=1), 9, "python"))     # ~4 MiB
    svc = _probe(host, monkeypatch)
    tracemalloc.start()
    try:
        d = svc.host_probe(["oom"], {"minutes": ["1440"]})
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert d["records_total"] == 1 and d["records"][0]["command"] == "python"
    assert peak < 1024 * 1024, peak                       # well under the 4 MiB read


def test_directory_walk_budget_fits_the_probe_memory_limit(host, monkeypatch):
    """Step 03: walking `/` to 50 000 entries charged 31 MiB of directory cache to the probe's 64 MiB cgroup."""
    assert _probe(host, monkeypatch).DIR_MAX_ENTRIES <= 20_000


def test_kernel_oom_records_without_a_kernel_log_are_unknown_not_zero(host, monkeypatch):
    d = _probe(host, monkeypatch).host_probe(["oom"], {"minutes": ["60"]})
    assert d["source"] == "unavailable" and d["records_total"] is None and d["records"] == []


def test_kernel_oom_window_is_bounded(host, monkeypatch):
    host.kern_log([])
    svc = _probe(host, monkeypatch)
    assert svc.host_probe(["oom"], {"minutes": ["99999"]})["window_minutes"] == 1440


# --- the capabilities (argus/capabilities/catalog.py) -----------------------------------------------
BATCH2 = {"host.load": "get_host_load", "host.io": "get_io_metrics", "host.top_cpu": "get_top_cpu_processes",
          "host.top_memory": "get_top_memory_processes", "host.socket_summary": "get_socket_summary",
          "host.directory_sizes": "get_directory_sizes", "host.kernel_oom_records": "get_kernel_oom_records"}


def _specs():
    from argus.capabilities.catalog import build_catalog
    return {s.name: s for s in build_catalog()}


def test_batch2_capabilities_are_level_2_on_the_host_probe_with_their_model_names():
    specs = _specs()
    for name, model_name in BATCH2.items():
        s = specs[name]
        assert (s.model_name, s.level, s.executor) == (model_name, 2, "host_probe"), name
        assert s.target_kinds == frozenset({"host"}), name
    for name in ("host.top_cpu", "host.top_memory", "host.kernel_oom_records"):     # process names
        assert specs[name].safety_class == "READ_ONLY_SENSITIVE", name


def test_policy_knows_every_batch2_capability():
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    for name in BATCH2:
        assert 1 <= pol["capabilities"][name]["max_per_incident"] <= 4, name


def test_each_class_is_offered_only_the_batch2_tools_that_serve_it():
    from argus.detectors.classes import CLASSES
    specs = _specs()
    offered = {c.name: {n for n in BATCH2 if specs[n].tags & c.tool_tags} for c in CLASSES}
    assert offered["cpu_saturation"] == {"host.load", "host.top_cpu"}
    assert offered["disk_pressure"] == {"host.io", "host.directory_sizes"}
    assert offered["container_restart_loop"] == {"host.top_memory", "host.kernel_oom_records"}
    assert not [c for c, o in offered.items() if "host.socket_summary" in o]       # no lab class needs host sockets
    assert offered["monitoring_blind_spot"] == set()


class _Client:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, path, params=None):
        self.calls.append((path, params))
        a = self.answers.get(path, self.answers.get("*"))
        if a is None:
            raise ExecutorError("not_found", path)
        return a


def _call(name, args, answers, info=None):
    from argus.domain.model import TargetInfo, TargetRef
    spec = _specs()[name]
    ref = TargetRef.parse(HOST)
    info = info or TargetInfo(ref=ref, mounts=["/", FILL])
    return spec.impl(spec.args_model.model_validate(args), ref, info, _Client(answers))


def test_batch2_texts_say_unknown_when_the_answer_lacks_their_keys():
    """The replay cases answer the host probe with one `"*"` row (cpu and memory keys only): a new route must read as
    unknown, never as zero or healthy."""
    star = {"*": {"total_mib": 5800, "available_mib": 3900, "cpu_busy_percent": 18, "load1": 0.4, "cpus": 2}}
    args = {"host.directory_sizes": {"mount": FILL}}
    for name in BATCH2:
        r = _call(name, args.get(name, {}), star)
        assert "unknown" in r.model_text, (name, r.model_text)


def test_top_cpu_text_names_commands_containers_and_the_sample():
    answer = {"/processes": {"by": "cpu", "sample_s": 0.5, "cpus": 2, "pids_read": 206, "truncated": False,
                             "processes": [{"pid": 4242, "command": "stress", "state": "R", "cpu_percent": 98.0,
                                            "rss_mib": 10.0, "container_id": CID[:12]},
                                           {"pid": 77, "command": "dockerd", "state": "S", "cpu_percent": 1.0,
                                            "rss_mib": 100.0, "container_id": None}],
                             "collected_at": "2026-10-12T06:00:00+00:00"}}
    r = _call("host.top_cpu", {"n": 2}, answer)
    for part in ("stress", f"container {CID[:12]}", "98.0%", "dockerd", "(host)", "one core"):
        assert part in r.model_text, part
    assert r.source_time is not None


def test_top_capabilities_ask_the_probe_for_their_order():
    from argus.domain.model import TargetInfo, TargetRef
    specs = _specs()
    ref = TargetRef.parse(HOST)
    for name, by in (("host.top_cpu", "cpu"), ("host.top_memory", "memory")):
        c = _Client({"*": {"processes": []}})
        specs[name].impl(specs[name].args_model.model_validate({"n": 3}), ref, TargetInfo(ref=ref), c)
        assert c.calls == [("/processes", {"by": by, "n": 3})], name


def test_kernel_oom_text_counts_records_and_names_the_latest():
    answer = {"/oom": {"source": "kern.log", "window_minutes": 60, "complete": True, "records_total": 12,
                       "by_container": [{"container_id": CID[:12], "count": 12}],
                       "records": [{"time": "2026-10-12T05:58:00+00:00", "scope": "memcg", "container_id": CID[:12],
                                    "command": "python", "pid": 2560725, "anon_rss_mib": 63.5}],
                       "oom_kill_since_boot": 18567, "collected_at": "2026-10-12T06:00:00+00:00"}}
    r = _call("host.kernel_oom_records", {"minutes": 60}, answer)
    for part in ("12 kernel OOM kill", "60 min", f"{CID[:12]}×12", "python", "63.5 MiB", "18567"):
        assert part in r.model_text, part
    none = {"/oom": {**answer["/oom"], "records_total": 0, "by_container": [], "records": []}}
    assert "no kernel OOM kill" in _call("host.kernel_oom_records", {}, none).model_text
    partial = {"/oom": {**none["/oom"], "complete": False}}
    assert "partial" in _call("host.kernel_oom_records", {}, partial).model_text


def test_directory_sizes_capability_refuses_an_undeclared_mount():
    with pytest.raises(ExecutorError) as e:
        _call("host.directory_sizes", {"mount": "/etc"}, {"*": {}})
    assert e.value.category == "invalid_args"


def test_directory_sizes_text_ranks_children_and_says_partial():
    answer = {"/directory_sizes": {"path": FILL, "complete": False, "entries_read": 50000, "limit_entries": 50000,
                                   "children": [{"name": "fill/", "mib": 5120.0, "entries": 3, "complete": True},
                                                {"name": "tmp/", "mib": 1.0, "entries": 9, "complete": False}],
                                   "collected_at": "2026-10-12T06:00:00+00:00"}}
    r = _call("host.directory_sizes", {"mount": FILL}, answer)
    assert "fill/ 5120.0 MiB" in r.model_text and "partial" in r.model_text and FILL in r.model_text


def test_container_status_shows_the_id_the_host_probe_uses():
    from argus.capabilities.catalog import NoArgs, container_status
    from argus.domain.model import TargetRef
    ref = TargetRef.parse("vm-166/container:argus-lab-api")

    class C:
        def __init__(self, d):
            self.d = d

        def get(self, path, params=None):
            return self.d
    assert f"id={CID[:12]}" in container_status(NoArgs(), ref, None, C({"id": CID[:12], "state": "running"})).model_text
    assert "id=" not in container_status(NoArgs(), ref, None, C({"state": "running"})).model_text


def test_argus_reads_the_host_load_through_invoke_capability(make_app):
    app = make_app()
    inc = incident(app, HOST)
    ctx = InvocationContext(incident=inc, caller="test", scope=app.runner.scope(inc.target))
    r = app.runner.invoke(ctx, "get_host_load", {"target": HOST})[0]
    assert r.status == "ok", r
    assert any(path == "/load" for _, path in FakeTargetAgent.calls)


# --- deployment check ---------------------------------------------------------------------------------
def test_phase3_check_exercises_every_new_route():
    text = (ROOT / "ops" / "phase3_check.py").read_text(encoding="utf-8")
    for route in ("/load", "/io", "/processes?by={by}", "/processes?by=disk", "/sockets",
                  "/directory_sizes?path=", "/directory_sizes?path=/etc", "/oom?minutes="):
        assert route in text, route
    assert 'for by in ("cpu", "memory")' in text


# --- the evaluation cases answer the new routes ---------------------------------------------------------------------
NEW_BY_CLASS = {"cpu_saturation": {"host.load": {}, "host.top_cpu": {"n": 5}},
                "disk_pressure": {"host.io": {}, "host.directory_sizes": {"mount": FILL},
                                  "host.directory_sizes /": {"mount": "/"}},
                "container_restart_loop": {"host.top_memory": {"n": 5}, "host.kernel_oom_records": {"minutes": 60}}}


def test_every_case_of_an_offered_class_answers_its_new_tools():
    """Step 03: the model asked `get_directory_sizes` 41 times in 24 disk runs and the cases answered only through
    their `"*"` row (unknown): `disk-filler-no-logs` then concluded 2 of 3 times (EVAL-2: 1 of 5). Each case of a class
    offered the new tools now answers them from its own story (labels unchanged)."""
    from argus.domain.model import TargetInfo, TargetRef
    from argus.evaluation.replay import FixtureExecutor
    specs = _specs()
    seen = 0
    for path in sorted((ROOT / "tests" / "eval" / "cases").glob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        tools = NEW_BY_CLASS.get(case["label"].get("class"))
        if not tools:
            continue
        host = case["target"].split("/")[0]
        ref = TargetRef.parse(f"{host}/host:{host}")
        client = FixtureExecutor(case["fixtures"].get("host_probe", {}))
        for name, args in tools.items():
            spec = specs[name.split()[0]]
            r = spec.impl(spec.args_model.model_validate(args), ref, TargetInfo(ref=ref, mounts=["/", FILL]), client)
            assert "unknown" not in r.model_text, (path.name, name, r.model_text)
            seen += 1
    assert seen >= 40


def test_the_system_prompt_says_where_the_space_went_is_not_who_wrote_it():
    """Step 03 (E.7): with `get_directory_sizes` answering "data-0007.bin 202 MiB", the model concluded in the abstain
    disk cases: it named the host ("the file is the cause") when the only container mounts read-only or wrote nothing,
    and the filler only because it could write there. A large file says where the space went, not who wrote it."""
    from argus.tooling.model_harness import SYSTEM_PROMPT
    text = " ".join(SYSTEM_PROMPT.split())
    assert "where the space went" in text and "not who wrote it" in text
    assert "only when the evidence ties it to the data" in text
    assert "can be the root cause of its own failure" in text            # EVAL-2's rule is still there


def test_an_evaluation_run_keeps_the_reason_of_each_invalid_decision(tmp_path):
    """Step 03 (E.9): one run of cpu-burner-05 made 7 invalid decisions in a row and ran out of steps; the results row
    said only `decision.invalid` x7, and 6 replays did not reproduce it. Each run now keeps the reasons."""
    from argus.adapters.outbound.llm import ScriptedLLM
    from argus.evaluation.cases import load_cases
    from argus.evaluation.replay import run_case
    c = next(x for x in load_cases(ROOT / "tests" / "eval" / "cases") if x.id == "restart-oom-01")
    calls = []

    def script(ctx: str):
        calls.append(1)
        if len(calls) == 1:
            return {"calls": [("get_magic_answer", {"target": c.target})]}          # not an offered tool
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "OOM-killed by its own 64 MiB memory limit",
                                        "evidence_ids": ids[-1:], "confidence": "high", "root_cause_target": c.target})]}
    run = run_case(c, tmp_path, llm=ScriptedLLM(script))
    assert run.invalid_decisions and run.invalid_decisions[0].startswith("fabricated_tool: ")
    assert "get_magic_answer" in run.invalid_decisions[0]
