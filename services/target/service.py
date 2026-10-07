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
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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


def inspect(name: str) -> dict:
    d = djson(f"/containers/{urllib.parse.quote(name)}/json")
    st, hc = d.get("State", {}), d.get("HostConfig", {})
    return {"id": d.get("Id", "")[:12], "name": name, "state": st.get("Status"), "running": st.get("Running"),
            "restart_count": d.get("RestartCount"), "oom_killed": st.get("OOMKilled"), "exit_code": st.get("ExitCode"),
            "started_at": st.get("StartedAt"), "finished_at": st.get("FinishedAt"), "error": st.get("Error") or None,
            "health": (st.get("Health") or {}).get("Status", "none"), "image": d.get("Config", {}).get("Image"),
            "memory_limit_bytes": hc.get("Memory") or None, "restart_policy": (hc.get("RestartPolicy") or {}).get("Name"),
            "tty": d.get("Config", {}).get("Tty"),
            # network names only (SC-07: which network is each side on?); addresses never leave the gateway
            "networks": sorted(((d.get("NetworkSettings") or {}).get("Networks") or {}).keys()),
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
        st = os.statvfs(ROOTFS + mount)
        total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        return {"mount": mount, "used_percent": round((1 - free / total) * 100, 1) if total else None,
                "free_mib": free // 2**20, "total_mib": total // 2**20,
                "inodes_used_percent": round((1 - st.f_ffree / st.f_files) * 100, 1) if st.f_files else None,
                "collected_at": now()}
    raise Err(404, "no such route")


def tcp(host: str, port: int, timeout: float = 3) -> dict:
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "duration_ms": round((time.monotonic() - t0) * 1000, 1)}
    except OSError as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "duration_ms": round((time.monotonic() - t0) * 1000, 1)}


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
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                code, err = r.status, None
        except urllib.error.HTTPError as e:
            code, err = e.code, None
        except (urllib.error.URLError, OSError) as e:
            code, err = None, str(getattr(e, "reason", e))
        return {"status": code, "error": err, "duration_ms": round((time.monotonic() - t0) * 1000, 1), "collected_at": now()}
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
    return {"database": name, "ok": True, "max_connections": st["max_connections"], "reserved_connections": reserved,
            "usable_connections": usable, "client_connections": total,
            "usage_percent": round(total * 100 / usable, 1) if usable > 0 else None, "by_state": by_state,
            "by_client": [{"application_name": a, "role": u, "connections": int(n)} for a, u, n in r["by_client"]],
            "longest_transactions": [{"pid": p, "application_name": a, "state": s, "wait_event_type": wt,
                                      "wait_event": we, "age_s": round(float(age), 1)}
                                     for p, a, s, wt, we, age in r["longest"]],
            "lock_waits": int(waits), "blocked_sessions": int(blocked), "collected_at": now()}


_metrics = "# no data yet\n"
_lock = threading.Lock()


def probe_lines(probes: list[dict], running: set[str]) -> list[str]:
    """Dependency probes of running owners only: a dependency of a container that does not run (an SC-07 client
    outside its scenario) is irrelevant, and a 0 would keep DependencyProbeFailed firing."""
    lines = []
    for p in probes:
        if p["owner"] not in running:
            continue
        r = tcp(p["host"], p["port"])
        lab = f'owner="{p["owner"]}",dependency="{p["dependency"]}"'
        lines += [f"argus_probe_success{{{lab}}} {1 if r['ok'] else 0}",
                  f"argus_probe_duration_seconds{{{lab}}} {r['duration_ms'] / 1000:.4f}"]
    return lines


def collect() -> None:
    global _metrics
    while True:
        lines, running = [], set()
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
            if d["health"] in ("healthy", "unhealthy", "starting"):
                lines.append(f"argus_container_health_unhealthy{{{lab}}} {1 if d['health'] == 'unhealthy' else 0}")
            if d["running"]:
                running.add(name)
                try:
                    s = stats(name, one_shot=True)
                    if s["memory_usage_bytes"] is not None:
                        lines.append(f"argus_container_memory_bytes{{{lab}}} {s['memory_usage_bytes']}")
                except Exception:
                    pass
        lines += probe_lines(CONFIG.get("probes", []), running)
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
