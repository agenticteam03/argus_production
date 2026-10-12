"""Argus v1.8 target-side services (v1.8 §4.4–§4.6). One codebase, ONE ROLE PER CONTAINER:

  ROLE=read_gateway   exact GET routes over this host's Docker socket          (token: docker_read)
  ROLE=host_probe     verbs over this host's /proc and allowlisted mounts       (token: host_probe)
  ROLE=network_probe  dns / tcp / http from the argus-lab-app network            (token: network_probe)
  ROLE=db_probe       health of allowlisted PostgreSQL databases, read-only role (token: db_probe)
  ROLE=exporter       /metrics for this host's Prometheus (no token, internal network only)

Exact routes only; allowlists from the rendered config (ops/render_target_config.py, from the inventory);
no shell; Config.Env is never returned; every JSON answer echoes `host` for attribution checks.
"""
from __future__ import annotations

import hmac
import http.client
import json
import os
import re
import socket
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROLE = os.environ["ROLE"]
CONFIG = json.load(open(os.environ.get("TA_CONFIG", "/etc/argus-v18/target.json")))
HOST = CONFIG["host"]
CONTAINERS = set(CONFIG.get("containers", []))
PROC = os.environ.get("TA_PROC", "/host/proc")
ROOTFS = os.environ.get("TA_ROOTFS", "/rootfs")
SECRETS = os.environ.get("TA_SECRETS", "/run/argus-v18")
SOCK = "/var/run/docker.sock"
TOKEN_NAME = {"read_gateway": "docker_read", "host_probe": "host_probe", "network_probe": "network_probe",
              "db_probe": "db_probe"}.get(ROLE)
TOKEN = open(f"{SECRETS}/{TOKEN_NAME}_token").read().strip() if TOKEN_NAME else None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Err(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code, self.msg = code, msg


# --- Docker Engine API (this host's socket only) ------------------------------------------------
class _Unix(http.client.HTTPConnection):
    def __init__(self, timeout: float = 10):
        super().__init__("localhost", timeout=timeout)

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(SOCK)
        self.sock = s


def docker(path: str, timeout: float = 10) -> tuple[int, bytes]:
    c = _Unix(timeout)
    try:
        c.request("GET", path)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


def djson(path: str):
    code, body = docker(path)
    if code == 404:
        raise Err(404, "container not found on this host")
    if code >= 300:
        raise Err(502, f"docker {code}")
    return json.loads(body)


def allowed(name: str) -> str:
    if name not in CONTAINERS:
        raise Err(404, "not in this host's allowlist")
    return name


def created_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def cpu_limit_cores(hc: dict) -> float | None:
    """The container's CPU limit in cores (T-0028, RB-006): `--cpus` (NanoCpus) or a CFS quota/period; None when
    unlimited or unknown."""
    if hc.get("NanoCpus"):
        return round(hc["NanoCpus"] / 1e9, 3)
    quota, period = hc.get("CpuQuota") or 0, hc.get("CpuPeriod") or 100_000
    return round(quota / period, 3) if quota > 0 else None


def host_mounts(mounts: list[dict], declared: list[str]) -> tuple[list[dict], int]:
    """E2E-3: the container's bind mounts, matched to the host's declared mounts (the longest prefix; `/` names
    nothing). Only a declared mount and rw/ro leave the gateway; any other bind is counted, never named."""
    named: dict[str, bool] = {}
    other = 0
    for m in mounts or []:
        if m.get("Type") != "bind":
            continue
        src = m.get("Source") or ""
        hits = [d for d in declared if d != "/" and (src == d or src.startswith(d.rstrip("/") + "/"))]
        if hits:
            best = max(hits, key=len)
            named[best] = named.get(best, False) or bool(m.get("RW"))
        else:
            other += 1
    return [{"mount": k, "rw": v} for k, v in sorted(named.items())], other


def inspect(name: str) -> dict:
    d = djson(f"/containers/{urllib.parse.quote(name)}/json")
    mounted, other_binds = host_mounts(d.get("Mounts") or [], CONFIG.get("mounts", []))
    st, hc = d.get("State", {}), d.get("HostConfig", {})
    return {"id": d.get("Id", "")[:12], "name": name, "state": st.get("Status"), "running": st.get("Running"),
            "restarting": st.get("Restarting"),
            "restart_count": d.get("RestartCount"), "created_at_seconds": created_seconds(d.get("Created")),
            "oom_killed": st.get("OOMKilled"), "exit_code": st.get("ExitCode"),
            "started_at": st.get("StartedAt"), "finished_at": st.get("FinishedAt"), "error": st.get("Error") or None,
            "health": (st.get("Health") or {}).get("Status", "none"), "image": d.get("Config", {}).get("Image"),
            "memory_limit_bytes": hc.get("Memory") or None, "cpu_limit_cores": cpu_limit_cores(hc),
            "restart_policy": (hc.get("RestartPolicy") or {}).get("Name"),
            "tty": d.get("Config", {}).get("Tty"),
            # network names only (SC-07: which network is each side on?); addresses never leave the gateway
            "networks": sorted(((d.get("NetworkSettings") or {}).get("Networks") or {}).keys()),
            # E2E-3: which declared host filesystems it has mounted (SC-05: the filler writes the lab filesystem)
            "host_mounts": mounted, "other_binds": other_binds,
            "collected_at": now()}


def demux(raw: bytes, tty: bool) -> list[str]:
    if tty:
        return raw.decode("utf-8", "replace").splitlines()
    out, i = [], 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out.append(raw[i + 8:i + 8 + size].decode("utf-8", "replace"))
        i += 8 + size
    return "".join(out).splitlines()


def stats(name: str, one_shot: bool = False) -> dict:
    s = djson(f"/containers/{urllib.parse.quote(name)}/stats?stream=false&one-shot={'true' if one_shot else 'false'}")
    m = s.get("memory_stats", {})
    usage = m.get("usage")
    if usage is not None:
        usage -= (m.get("stats") or {}).get("inactive_file", 0)
    limit = m.get("limit")
    cpu, pre = s.get("cpu_stats", {}), s.get("precpu_stats", {})
    pct = None
    try:
        dc = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
        ds = cpu["system_cpu_usage"] - pre["system_cpu_usage"]
        pct = round(dc / ds * cpu.get("online_cpus", 1) * 100, 2) if ds > 0 else None
    except (KeyError, TypeError):
        pass
    return {"memory_usage_bytes": usage, "memory_limit_bytes": limit,
            "memory_percent": round(usage / limit * 100, 1) if usage and limit else None,
            "cpu_percent": pct, "pids": (s.get("pids_stats") or {}).get("current"), "collected_at": now()}


def container_events(name: str, minutes: int) -> list[dict]:
    until = int(time.time())
    flt = urllib.parse.quote(json.dumps({"container": [name], "type": ["container"]}))
    _, raw = docker(f"/events?since={until - minutes * 60}&until={until}&filters={flt}", timeout=15)
    evs = []
    for line in raw.decode("utf-8", "replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        evs.append({"time": e.get("time"), "action": e.get("Action") or e.get("status"),
                    "exit_code": ((e.get("Actor") or {}).get("Attributes") or {}).get("exitCode")})
    return evs


def last_exit(d: dict, evs: list[dict]) -> tuple[int, bool]:
    """(exit code, OOM-killed) of the LAST exit. Docker resets State.ExitCode/OOMKilled when a restarted container
    runs again, so for a running container the last `die` event (and an `oom` event just before it) is the truth."""
    if not d["running"]:
        return int(d["exit_code"] or 0), bool(d["oom_killed"])
    dies = [i for i, e in enumerate(evs) if e["action"] == "die"]
    if not dies:
        return int(d["exit_code"] or 0), bool(d["oom_killed"])
    i = dies[-1]
    prev = dies[-2] if len(dies) > 1 else -1
    oom = any(e["action"] == "oom" for e in evs[prev + 1:i + 1])
    try:
        code = int(evs[i]["exit_code"] or 0)
    except (TypeError, ValueError):
        code = 0
    return code, oom


def read_gateway(parts: list[str], q: dict) -> dict:
    if parts == ["containers"]:
        rows = json.loads(docker("/containers/json?all=1")[1])
        out = [{"name": n.lstrip("/"), "state": r.get("State"), "status": r.get("Status"), "image": r.get("Image")}
               for r in rows for n in r.get("Names", [])[:1] if n.lstrip("/") in CONTAINERS]
        return {"containers": out, "collected_at": now()}
    if len(parts) == 3 and parts[0] == "containers":
        name, what = allowed(parts[1]), parts[2]
        if what == "status":
            return inspect(name)
        if what == "health":
            h = djson(f"/containers/{name}/json").get("State", {}).get("Health") or {}
            return {"status": h.get("Status", "none"), "failing_streak": h.get("FailingStreak"),
                    "log": [{"exit_code": e.get("ExitCode"), "output": (e.get("Output") or "")[:300], "end": e.get("End")}
                            for e in (h.get("Log") or [])[-3:]], "collected_at": now()}
        if what == "logs":
            tail = max(1, min(200, int(q.get("tail", ["50"])[0])))
            code, raw = docker(f"/containers/{name}/logs?stdout=1&stderr=1&timestamps=1&tail={tail}")
            if code >= 300:
                raise Err(502, f"docker logs {code}")
            return {"lines": [ln[:500] for ln in demux(raw, bool(inspect(name)["tty"]))][-tail:], "truncated": False,
                    "collected_at": now()}
        if what == "stats":
            return stats(name)
        if what == "events":
            evs = container_events(name, max(1, min(120, int(q.get("minutes", ["30"])[0]))))
            return {"events": evs[-200:], "truncated": len(evs) > 200, "collected_at": now()}
    raise Err(404, "no such route")


def _cpu_times() -> tuple[int, int]:
    vals = list(map(int, open(f"{PROC}/stat").readline().split()[1:]))
    return sum(vals), vals[3] + (vals[4] if len(vals) > 4 else 0)


def host_probe(parts: list[str], q: dict) -> dict:
    if parts == ["cpu"]:
        t1, i1 = _cpu_times()
        time.sleep(0.5)
        t2, i2 = _cpu_times()
        load = open(f"{PROC}/loadavg").read().split()
        cpus = sum(1 for ln in open(f"{PROC}/stat") if ln.startswith("cpu") and ln[3].isdigit())
        return {"cpu_busy_percent": round((1 - (i2 - i1) / max(t2 - t1, 1)) * 100, 1), "load1": float(load[0]),
                "load5": float(load[1]), "cpus": cpus, "collected_at": now()}
    if parts == ["memory"]:
        mi = {}
        for ln in open(f"{PROC}/meminfo"):
            k, v = ln.split(":", 1)
            mi[k] = int(v.split()[0]) // 1024
        return {"total_mib": mi.get("MemTotal"), "available_mib": mi.get("MemAvailable"),
                "swap_used_mib": mi.get("SwapTotal", 0) - mi.get("SwapFree", 0), "collected_at": now()}
    if parts == ["uptime"]:
        return {"uptime_seconds": float(open(f"{PROC}/uptime").read().split()[0]), "collected_at": now()}
    if parts == ["disk"]:
        mount = q.get("mount", ["/"])[0]
        if mount not in CONFIG.get("mounts", []):
            raise Err(400, "mount not allowlisted")
        if mount != "/" and not os.path.ismount(ROOTFS + mount):
            raise Err(409, f"{mount} is not mounted (unknown, not the root disk)")      # T-0024
        st = os.statvfs(ROOTFS + mount)
        total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        return {"mount": mount, "used_percent": round((1 - free / total) * 100, 1) if total else None,
                "free_mib": free // 2**20, "total_mib": total // 2**20,
                "inodes_used_percent": round((1 - st.f_ffree / st.f_files) * 100, 1) if st.f_files else None,
                "collected_at": now()}
    # T-0019 batch 2: diagnosis verbs (§4.6). Only what this container already mounts read-only; never a process's
    # command line or environment, never a network address; a missing source is unknown, not zero.
    if parts == ["load"]:
        la = open(f"{PROC}/loadavg").read().split()
        runnable, threads = la[3].split("/")
        return {"load1": float(la[0]), "load5": float(la[1]), "load15": float(la[2]), "runnable": int(runnable),
                "threads": int(threads), "cpus": _cpus(), "pressure": {k: psi(k) for k in ("cpu", "memory", "io")},
                "collected_at": now()}
    if parts == ["io"]:
        return io_rates()
    if parts == ["processes"]:
        by = q.get("by", ["cpu"])[0]
        if by not in ("cpu", "memory"):
            raise Err(400, "by must be cpu or memory")
        return top_processes(by, _int_arg(q, "n", 5, 1, PROCESS_MAX_N))
    if parts == ["sockets"]:
        return socket_summary()
    if parts == ["directory_sizes"]:
        return directory_sizes(q.get("path", [""])[0])
    if parts == ["oom"]:
        return kernel_oom_records(_int_arg(q, "minutes", 60, 1, OOM_MAX_MINUTES))
    raise Err(404, "no such route")


def _int_arg(q: dict, name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(q.get(name, [str(default)])[0])))
    except ValueError:
        raise Err(400, f"{name} must be an integer")


def _cpus() -> int:
    return sum(1 for ln in open(f"{PROC}/stat") if ln.startswith("cpu") and ln[3].isdigit())


def psi(kind: str) -> dict | None:
    """Pressure stall information (/proc/pressure/<kind>): the share of time tasks waited, `some` and `full`."""
    try:
        lines = open(f"{PROC}/pressure/{kind}").read().splitlines()
    except OSError:
        return None                                  # no PSI on this kernel: unknown
    out = {}
    for ln in lines:
        head, *kv = ln.split()
        vals = dict(x.split("=", 1) for x in kv)
        out[head] = {k: float(vals[k]) for k in ("avg10", "avg60", "avg300") if k in vals}
    return out


IO_SAMPLE_S, IO_MAX_DEVICES = 1.0, 8


def _diskstats(devices: list[str]) -> dict[str, list[int]]:
    out = {}
    for ln in open(f"{PROC}/diskstats"):
        f = ln.split()
        if len(f) >= 14 and f[2] in devices:
            out[f[2]] = [int(x) for x in f[3:14]]
    return out


def io_rates() -> dict:
    """Whole block devices (/sys/block, no loop or RAM disks), /proc/diskstats sampled IO_SAMPLE_S apart."""
    try:
        devices = [d for d in sorted(os.listdir(f"{ROOTFS}/sys/block")) if not d.startswith(("loop", "ram", "zram"))]
    except OSError:
        devices = []
    devices = devices[:IO_MAX_DEVICES]
    a = _diskstats(devices)
    time.sleep(IO_SAMPLE_S)
    b = _diskstats(devices)
    rows = []
    for d in devices:
        if d not in a or d not in b:
            continue
        x = [j - i for i, j in zip(a[d], b[d])]
        rows.append({"device": d, "reads_s": round(x[0] / IO_SAMPLE_S, 1), "writes_s": round(x[4] / IO_SAMPLE_S, 1),
                     "read_kib_s": round(x[2] * 512 / 1024 / IO_SAMPLE_S, 1),
                     "write_kib_s": round(x[6] * 512 / 1024 / IO_SAMPLE_S, 1),
                     "busy_percent": round(min(100.0, x[9] / (IO_SAMPLE_S * 1000) * 100), 1)})
    return {"devices": rows, "interval_s": IO_SAMPLE_S, "pressure": psi("io"), "collected_at": now()}


PROCESS_MAX_N, PROCESS_MAX_PIDS, PROCESS_SAMPLE_S = 10, 4096, 0.5
CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE_BYTES = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
_CONTAINER_ID = re.compile(r"docker[-/]([0-9a-f]{64})")


def _processes() -> tuple[dict[int, dict], int]:
    """/proc/<pid>/stat only: the command name (comm), state, parent, CPU ticks and RSS. Never cmdline or environ."""
    pids = sorted(int(p) for p in os.listdir(PROC) if p.isdigit())
    snap = {}
    for pid in pids[:PROCESS_MAX_PIDS]:
        try:
            raw = open(f"{PROC}/{pid}/stat").read()
        except OSError:
            continue                                 # the process ended
        head, _, rest = raw.rpartition(")")
        f = rest.split()
        if "(" not in head or len(f) < 22:
            continue
        snap[pid] = {"command": head.split("(", 1)[1][:15], "state": f[0], "ppid": int(f[1]),
                     "ticks": int(f[11]) + int(f[12]), "rss_pages": int(f[21])}
    return snap, len(pids)


def _container_of(pid: int) -> str | None:
    try:
        m = _CONTAINER_ID.search(open(f"{PROC}/{pid}/cgroup").read())
    except OSError:
        return None
    return m.group(1)[:12] if m else None


def top_processes(by: str, n: int) -> dict:
    a, total = _processes()
    if by == "cpu":
        time.sleep(PROCESS_SAMPLE_S)
        b, total = _processes()
        rank = {p: (b[p]["ticks"] - a[p]["ticks"]) / CLK_TCK / PROCESS_SAMPLE_S * 100 for p in b if p in a}
    else:
        b = a
        rank = {p: b[p]["rss_pages"] for p in b}
    rows = []
    for pid in sorted(rank, key=lambda p: (-rank[p], p))[:n]:
        p = b[pid]
        row = {"pid": pid, "command": p["command"], "state": p["state"],
               "rss_mib": round(p["rss_pages"] * PAGE_BYTES / 2**20, 1), "container_id": _container_of(pid),
               "kernel_thread": pid == 2 or p["ppid"] == 2}
        if by == "cpu":
            row["cpu_percent"] = round(rank[pid], 1)
        rows.append(row)
    return {"by": by, "processes": rows, "pids_read": min(total, PROCESS_MAX_PIDS),
            "truncated": total > PROCESS_MAX_PIDS, "cpus": _cpus(),
            "sample_s": PROCESS_SAMPLE_S if by == "cpu" else None, "collected_at": now()}


TCP_STATES = {"01": "established", "02": "syn_sent", "03": "syn_recv", "04": "fin_wait1", "05": "fin_wait2",
              "06": "time_wait", "07": "close", "08": "close_wait", "09": "last_ack", "0A": "listen", "0B": "closing",
              "0C": "new_syn_recv"}
SOCKET_MAX_LINES, SOCKET_MAX_PORTS = 65536, 20


def socket_summary() -> dict:
    """The host's network namespace (pid 1's), not this container's: counts by state and listening ports only."""
    base = f"{PROC}/1/net"
    try:
        sockstat = open(f"{base}/sockstat").read().splitlines()
    except OSError:
        raise Err(503, "the host network namespace (pid 1) is not readable")
    by_state: dict[str, int] = {}
    listening: set[int] = set()
    read = 0
    for fam in ("tcp", "tcp6"):
        try:
            lines = open(f"{base}/{fam}").read().splitlines()[1:]
        except OSError:
            continue
        for ln in lines[:max(0, SOCKET_MAX_LINES - read)]:
            f = ln.split()
            if len(f) < 4:
                continue
            read += 1
            state = TCP_STATES.get(f[3], f[3])
            by_state[state] = by_state.get(state, 0) + 1
            if state == "listen":
                listening.add(int(f[1].rsplit(":", 1)[1], 16))
    totals = {}
    for ln in sockstat:
        proto, _, rest = ln.partition(":")
        v = rest.split()
        totals[proto] = {k: int(x) for k, x in zip(v[::2], v[1::2]) if x.isdigit()}
    return {"namespace": "host (pid 1)", "tcp_by_state": by_state,
            "listening_ports": sorted(listening)[:SOCKET_MAX_PORTS], "listening_ports_total": len(listening),
            "sockets_read": read, "truncated": read >= SOCKET_MAX_LINES, "sockstat": totals, "collected_at": now()}


DIR_MAX_ENTRIES, DIR_MAX_SECONDS, DIR_MAX_CHILDREN = 50_000, 4.0, 10


def _usage(st: os.stat_result) -> int:
    blocks = getattr(st, "st_blocks", None)
    return blocks * 512 if blocks is not None else st.st_size


def directory_sizes(path: str) -> dict:
    """The largest direct children of a declared mount: one filesystem, symlinks not followed, bounded in entries
    and time (`complete: false` says the walk was cut)."""
    if path not in CONFIG.get("mounts", []):
        raise Err(400, "path is not a declared mount")
    base = ROOTFS + path
    if path != "/" and not os.path.ismount(base):
        raise Err(409, f"{path} is not mounted (unknown, not the root disk)")
    dev = os.lstat(base).st_dev
    deadline = time.monotonic() + DIR_MAX_SECONDS
    read, other_fs, complete, children = 0, 0, True, []

    def budget_left() -> bool:
        return read < DIR_MAX_ENTRIES and time.monotonic() < deadline

    for entry in sorted(os.scandir(base), key=lambda e: e.name):
        if not budget_left():
            complete = False
            break
        try:
            st = os.lstat(entry.path)
        except OSError:
            continue
        read += 1
        if st.st_dev != dev:
            other_fs += 1                            # another filesystem mounted here: not this mount's usage
            continue
        size, entries, done = _usage(st), 1, True
        is_dir = stat.S_ISDIR(st.st_mode)
        stack = [entry.path] if is_dir else []
        while stack and done:
            try:
                inner = list(os.scandir(stack.pop()))
            except OSError:
                continue
            for e in inner:
                if not budget_left():
                    done = False
                    break
                try:
                    s = os.lstat(e.path)
                except OSError:
                    continue
                read += 1
                if s.st_dev != dev:
                    continue
                size, entries = size + _usage(s), entries + 1
                if stat.S_ISDIR(s.st_mode):
                    stack.append(e.path)
        complete = complete and done
        row = {"name": entry.name + ("/" if is_dir else ""), "bytes": size, "entries": entries, "complete": done}
        if stat.S_ISLNK(st.st_mode):
            row["symlink"] = True                    # its own size only; never followed
        children.append(row)
    children.sort(key=lambda c: (-c["bytes"], c["name"]))
    for c in children:
        c["mib"] = round(c.pop("bytes") / 2**20, 1)
    return {"path": path, "children": children[:DIR_MAX_CHILDREN], "children_read": len(children),
            "other_filesystems": other_fs, "complete": complete, "entries_read": read,
            "limit_entries": DIR_MAX_ENTRIES, "limit_seconds": DIR_MAX_SECONDS, "collected_at": now()}


OOM_MAX_BYTES, OOM_MAX_RECORDS, OOM_MAX_MINUTES = 4 * 2**20, 10, 1440
_MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
_KERNEL_LINE = re.compile(r"^(?:(\w{3}) +(\d{1,2}) (\d\d):(\d\d):(\d\d)|(\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:?\d\d)?))"
                          r" \S+ kernel: (?:\[ *[\d.]+\] )?(.*)$")
_KILLED = re.compile(r"Killed process (\d+) \(.*?\).*?anon-rss:(\d+)kB")


def _kernel_time(m: re.Match, ref: datetime) -> datetime | None:
    if m.group(6):
        t = datetime.fromisoformat(m.group(6).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    month = _MONTHS.get(m.group(1))
    if not month:
        return None
    t = datetime(ref.year, month, int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)),
                 tzinfo=timezone.utc)
    return t.replace(year=ref.year - 1) if t > ref + timedelta(days=1) else t     # the traditional format has no year


def _kernel_tail(path: str, ref: datetime) -> tuple[list[tuple[datetime, str]], bool]:
    """The kernel lines of the last OOM_MAX_BYTES of a log file, and whether the file is longer than that."""
    size = os.path.getsize(path)
    start = max(0, size - OOM_MAX_BYTES)
    with open(path, "rb") as f:
        f.seek(start)
        lines = f.read(OOM_MAX_BYTES).decode("utf-8", "replace").splitlines()
    if start:
        lines = lines[1:]                            # the first line was cut
    out = []
    for ln in lines:
        m = _KERNEL_LINE.match(ln)
        t = _kernel_time(m, ref) if m else None
        if t:
            out.append((t, m.group(7)))
    return out, start > 0


def _vmstat_oom_kill() -> int | None:
    try:
        for ln in open(f"{PROC}/vmstat"):
            if ln.startswith("oom_kill "):
                return int(ln.split()[1])
    except OSError:
        pass
    return None


def kernel_oom_records(minutes: int) -> dict:
    """Kernel OOM-killer records from rsyslog's text copy of the kernel log (kern.log, then kern.log.1), read from
    the end and bounded: the probe has no journalctl, and /dev/kmsg needs CAP_SYSLOG."""
    ref = datetime.now(timezone.utc)
    since = ref - timedelta(minutes=minutes)
    files = [f"{ROOTFS}/var/log/{n}" for n in ("kern.log", "kern.log.1")]
    base = {"window_minutes": minutes, "oom_kill_since_boot": _vmstat_oom_kill(), "collected_at": now()}
    if not any(os.path.exists(p) for p in files):
        return {**base, "source": "unavailable", "complete": False, "records_total": None, "by_container": [],
                "records": []}
    chunks: list[list[tuple[datetime, str]]] = []
    complete = None
    for p in files:                                  # newest first; stop once the window is covered
        if not os.path.exists(p):
            continue
        lines, cut = _kernel_tail(p, ref)
        chunks.insert(0, lines)
        if lines and lines[0][0] <= since:
            complete = True
            break
        if cut:
            complete = False                         # the window starts before what was read
            break
    if complete is None:                             # both files read whole; older ones are compressed, not read
        complete = not os.path.exists(f"{ROOTFS}/var/log/kern.log.2.gz")
    records: list[dict] = []
    for t, msg in (x for chunk in chunks for x in chunk):
        if t < since:
            continue
        if msg.startswith("oom-kill:"):
            kv = dict(i.split("=", 1) for i in msg[len("oom-kill:"):].split(",") if "=" in i)
            cid = _CONTAINER_ID.search(kv.get("task_memcg", "") + " " + kv.get("cpuset", ""))
            pid = kv.get("pid", "")
            records.append({"time": t.isoformat(), "scope": "memcg" if kv.get("constraint") == "CONSTRAINT_MEMCG"
                            else "host", "container_id": cid.group(1)[:12] if cid else None,
                            "command": kv.get("task", "")[:15], "pid": int(pid) if pid.isdigit() else None,
                            "anon_rss_mib": None})
            continue
        k = _KILLED.search(msg)
        if k:
            for r in reversed(records):
                if r["pid"] == int(k.group(1)) and r["anon_rss_mib"] is None:
                    r["anon_rss_mib"] = round(int(k.group(2)) / 1024, 1)
                    break
    counts: dict[str | None, int] = {}
    for r in records:
        counts[r["container_id"]] = counts.get(r["container_id"], 0) + 1
    by_container = [{"container_id": c, "count": n} for c, n in sorted(counts.items(), key=lambda x: -x[1])][:5]
    return {**base, "source": "kern.log", "complete": complete, "records_total": len(records),
            "by_container": by_container, "records": records[-OOM_MAX_RECORDS:]}


def tcp(host: str, port: int, timeout: float = 3) -> dict:
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "duration_ms": round((time.monotonic() - t0) * 1000, 1)}
    except OSError as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "duration_ms": round((time.monotonic() - t0) * 1000, 1)}


def http_check(url: str, timeout: float = 5) -> dict:
    """One GET of an allowlisted URL: the status code (None when nothing answered), the error, the duration."""
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            code, err = r.status, None
    except urllib.error.HTTPError as e:
        code, err = e.code, None
    except (urllib.error.URLError, OSError) as e:
        code, err = None, str(getattr(e, "reason", e))
    return {"status": code, "error": err, "duration_ms": round((time.monotonic() - t0) * 1000, 1)}


def network_probe(parts: list[str], q: dict) -> dict:
    if parts == ["dns"]:
        name = q.get("name", [""])[0]
        if name not in CONFIG.get("dns_names", []):
            raise Err(400, "name not allowlisted")
        try:
            return {"ok": True, "addresses": sorted({a[4][0] for a in socket.getaddrinfo(name, None)}), "collected_at": now()}
        except OSError as e:
            return {"ok": False, "error": str(e), "collected_at": now()}
    if parts == ["tcp"]:
        host, port = q.get("host", [""])[0], int(q.get("port", ["0"])[0])
        if [host, port] not in CONFIG.get("tcp", []):
            raise Err(400, "host:port not allowlisted")
        return {**tcp(host, port), "collected_at": now()}
    if parts == ["http"]:
        url = q.get("url", [""])[0]
        if url not in CONFIG.get("http_endpoints", []):
            raise Err(400, "url not allowlisted")
        return {**http_check(url), "collected_at": now()}
    raise Err(404, "no such route")


# --- db_probe: PostgreSQL health through a monitoring role (pg_monitor only) -----------------------
# System views only; never business rows, never the `query` column (SQL text can hold data and secrets).
_CLIENTS = "backend_type = 'client backend' AND pid <> pg_backend_pid()"
DB_QUERIES = {
    "settings": "SELECT name, setting FROM pg_settings WHERE name IN "
                "('max_connections', 'superuser_reserved_connections', 'reserved_connections')",
    "by_state": f"SELECT coalesce(state, 'unknown'), count(*) FROM pg_stat_activity WHERE {_CLIENTS} GROUP BY 1",
    "by_client": "SELECT coalesce(nullif(application_name, ''), '(none)'), usename, count(*) FROM pg_stat_activity "
                 f"WHERE {_CLIENTS} GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10",
    "longest": "SELECT pid, coalesce(nullif(application_name, ''), '(none)'), state, wait_event_type, wait_event, "
               "extract(epoch FROM now() - xact_start)::float FROM pg_stat_activity "
               f"WHERE {_CLIENTS} AND xact_start IS NOT NULL ORDER BY xact_start LIMIT 5",
    "locks": "SELECT (SELECT count(*) FROM pg_locks WHERE NOT granted), "
             "(SELECT count(*) FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0)",
    # OP-010: does this role own a reserved slot (PG 16)? The role is absent before 16: zero rows, no error.
    "reserved_slot": "SELECT count(*) FROM pg_roles WHERE rolname = 'pg_use_reserved_connections' "
                     "AND pg_has_role(current_user, oid, 'MEMBER')",
}


def pg_connect(db: dict):
    import pg8000.native                     # only the db image (Dockerfile target `db`) carries the driver
    password = open(f"{SECRETS}/db_monitor_password").read().strip()
    return pg8000.native.Connection(user=db.get("user", "argus_monitor"), password=password, host=db["host"],
                                    port=db["port"], database=db["dbname"], timeout=5,
                                    application_name="argus-db-probe")


def db_probe(parts: list[str], q: dict) -> dict:
    if parts != ["database", "health"]:
        raise Err(404, "no such route")
    name = q.get("name", [""])[0]
    db = next((d for d in CONFIG.get("databases", []) if d["name"] == name), None)
    if db is None:
        raise Err(400, "database not allowlisted")
    return db_health(db)


def db_metrics() -> str:
    """Slot usage of every allowlisted database for Prometheus (T-0020). Computed at scrape time: one short
    connection per database. A database that cannot be read has only `argus_db_up 0` (unknown, never zero)."""
    lines = []
    for db in CONFIG.get("databases", []):
        lab = f'container="{db["name"]}"'
        try:
            h = db_health(db)
        except Exception:               # also a query that fails after connecting (statement_timeout, lost link)
            lines.append(f"argus_db_up{{{lab}}} 0")
            continue
        oldest = max([t["age_s"] for t in h["longest_transactions"]], default=0)
        lines += [f"argus_db_up{{{lab}}} 1", f"argus_db_connections_max{{{lab}}} {h['max_connections']}",
                  f"argus_db_connections_usable{{{lab}}} {h['usable_connections']}",
                  f"argus_db_connections_used{{{lab}}} {h['client_connections']}",
                  *(f'argus_db_connections{{{lab},state="{s}"}} {n}' for s, n in sorted(h["by_state"].items())),
                  f"argus_db_oldest_xact_seconds{{{lab}}} {oldest}", f"argus_db_lock_waits{{{lab}}} {h['lock_waits']}",
                  f"argus_db_monitor_slot_reserved{{{lab}}} {1 if h['monitor_slot_reserved'] else 0}"]
    return "\n".join(lines) + "\n"


def db_health(db: dict) -> dict:
    name = db["name"]
    try:
        conn = pg_connect(db)
    except Exception as e:
        raise Err(502, f"database unreachable: {type(e).__name__}")
    try:
        conn.run("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        conn.run("SET statement_timeout = '3s'")
        r = {k: conn.run(sql) for k, sql in DB_QUERIES.items()}
    finally:
        conn.close()
    st = {k: int(v) for k, v in r["settings"]}
    reserved = st.get("superuser_reserved_connections", 0) + st.get("reserved_connections", 0)
    usable = st["max_connections"] - reserved
    by_state = {s: int(n) for s, n in r["by_state"]}
    total = sum(by_state.values())
    waits, blocked = r["locks"][0]
    # OP-010: without a slot of its own the probe is locked out exactly when every ordinary slot is taken
    member = bool(r["reserved_slot"] and int(r["reserved_slot"][0][0]))
    return {"database": name, "ok": True, "max_connections": st["max_connections"], "reserved_connections": reserved,
            "usable_connections": usable, "client_connections": total,
            "usage_percent": round(total * 100 / usable, 1) if usable > 0 else None, "by_state": by_state,
            "by_client": [{"application_name": a, "role": u, "connections": int(n)} for a, u, n in r["by_client"]],
            "longest_transactions": [{"pid": p, "application_name": a, "state": s, "wait_event_type": wt,
                                      "wait_event": we, "age_s": round(float(age), 1)}
                                     for p, a, s, wt, we, age in r["longest"]],
            "lock_waits": int(waits), "blocked_sessions": int(blocked),
            "monitor_slot_reserved": member and st.get("reserved_connections", 0) > 0, "collected_at": now()}


_metrics = "# no data yet\n"
_lock = threading.Lock()


def owner_active(d: dict) -> bool:
    """Running, or restarting (OP-007): an owner that crash-loops because its dependency is down waits in Docker's
    `restarting` state most of the time, and its probe is then the evidence of the real cause."""
    return bool(d.get("running") or d.get("restarting"))


def probe_lines(probes: list[dict], active: set[str]) -> list[str]:
    """Dependency probes of active owners only (owner_active): a dependency of a container that is missing or stopped
    (an SC-07 client outside its scenario) is irrelevant, and a 0 would keep DependencyProbeFailed firing."""
    lines = []
    for p in probes:
        if p["owner"] not in active:
            continue
        r = tcp(p["host"], p["port"])
        lab = f'owner="{p["owner"]}",dependency="{p["dependency"]}"'
        lines += [f"argus_probe_success{{{lab}}} {1 if r['ok'] else 0}",
                  f"argus_probe_duration_seconds{{{lab}}} {r['duration_ms'] / 1000:.4f}"]
    return lines


GATEWAY_ERRORS = (502, 504)    # the proxy's own answers when its upstream fails or is too slow (an app's 503 is not)


def http_probe_lines(probes: list[dict], active: set[str]) -> list[str]:
    """T-0029: a synthetic GET of every declared endpoint of an active owner (SC-08 runs only during its scenario).
    `gateway_error` is 1 for 502/504: the proxy could not get an answer from its upstream (RB-015)."""
    lines = []
    for p in probes:
        if p["owner"] not in active:
            continue
        r = http_check(p["url"])
        lab = f'owner="{p["owner"]}",url="{p["url"]}"'
        lines += [f"argus_http_probe_status{{{lab}}} {r['status'] or 0}",
                  f"argus_http_probe_gateway_error{{{lab}}} {1 if r['status'] in GATEWAY_ERRORS else 0}",
                  f"argus_http_probe_duration_seconds{{{lab}}} {r['duration_ms'] / 1000:.4f}"]
    return lines


def collect() -> None:
    global _metrics
    while True:
        lines, active = [], set()
        for name in sorted(CONTAINERS):
            try:
                d = inspect(name)
            except Exception:
                continue                     # absent ⇒ no series (unknown, never zero)
            lab = f'container="{name}"'
            try:
                code, oom = last_exit(d, container_events(name, 10))
            except Exception:
                code, oom = int(d["exit_code"] or 0), bool(d["oom_killed"])
            lines += [f"argus_container_restart_count{{{lab}}} {d['restart_count'] or 0}",
                      f"argus_container_oom_killed{{{lab}}} {1 if oom else 0}",
                      f"argus_container_last_exit_code{{{lab}}} {code}",
                      f"argus_container_running{{{lab}}} {1 if d['running'] else 0}"]
            if d.get("created_at_seconds") is not None:
                lines.append(f"argus_container_created_seconds{{{lab}}} {d['created_at_seconds']}")
            if d["health"] in ("healthy", "unhealthy", "starting"):
                lines.append(f"argus_container_health_unhealthy{{{lab}}} {1 if d['health'] == 'unhealthy' else 0}")
            if owner_active(d):
                active.add(name)
            if d["running"]:
                try:
                    s = stats(name, one_shot=True)
                    if s["memory_usage_bytes"] is not None:
                        lines.append(f"argus_container_memory_bytes{{{lab}}} {s['memory_usage_bytes']}")
                except Exception:
                    pass
        lines += probe_lines(CONFIG.get("probes", []), active)
        lines += http_probe_lines(CONFIG.get("http_probes", []), active)
        with _lock:
            _metrics = "\n".join(lines) + "\n"
        time.sleep(10)


ROUTES = {"read_gateway": read_gateway, "host_probe": host_probe, "network_probe": network_probe, "db_probe": db_probe}


class Handler(BaseHTTPRequestHandler):
    server_version = f"argus-v18-{ROLE}/1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        parts = [p for p in u.path.split("/") if p]
        try:
            if parts == ["healthz"]:
                return self._send(200, json.dumps({"ok": True, "role": ROLE, "host": HOST}).encode())
            if ROLE == "exporter":
                if parts == ["metrics"]:
                    with _lock:
                        return self._send(200, _metrics.encode(), "text/plain; version=0.0.4")
                raise Err(404, "no such route")
            given = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given, TOKEN):
                raise Err(401, "unauthorized")
            if ROLE == "db_probe" and parts == ["metrics"]:      # scraped by this host's Prometheus with the token
                return self._send(200, db_metrics().encode(), "text/plain; version=0.0.4")
            body = ROUTES[ROLE](parts, urllib.parse.parse_qs(u.query))
            self._send(200, json.dumps({**body, "host": HOST, "role": ROLE}, default=str).encode())
        except Err as e:
            self._send(e.code, json.dumps({"error": e.msg, "host": HOST}).encode())
        except Exception as e:  # never leak stack traces
            self._send(500, json.dumps({"error": type(e).__name__, "host": HOST}).encode())

    def do_POST(self):
        self._send(405, b'{"error": "read-only"}')

    do_PUT = do_DELETE = do_PATCH = do_POST


if __name__ == "__main__":
    if ROLE == "exporter":
        threading.Thread(target=collect, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8700), Handler).serve_forever()
