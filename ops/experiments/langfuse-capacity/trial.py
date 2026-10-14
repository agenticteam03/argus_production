"""Temporary, bounded, synthetic-only Langfuse capacity trial; run as root on vm-095."""
import base64
import json
import os
import re
from pathlib import Path
import secrets
import statistics
import subprocess
import threading
import time
import urllib.request
import urllib.parse
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
ENV = ROOT / "trial.env"
COMPOSE = ROOT / "compose.yaml"
PROJECT = "argus-lab-lf1"
NAMES = [PROJECT + "-" + x for x in ("postgres", "redis", "minio", "clickhouse", "web", "worker")]
VOLUMES = [PROJECT + "-" + x for x in ("pgdata", "redisdata", "s3data", "chdata", "chlogs")]
CORE = ["argus-v18-" + x for x in ("agent", "worker", "scheduler", "postgres", "ui")]
report = {"kind": "synthetic-capacity-only", "phases": {}, "samples": []}
stop = threading.Event()
phase = "baseline"

def run(args, timeout=90, check=True):
    p = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError("command failed: " + args[0] + " returncode=" + str(p.returncode))
    return p

def docker(*args, **kw):
    return run(["docker", *args], **kw)

def dc(*args, **kw):
    return run(["docker", "compose", "--project-name", PROJECT, "--env-file", str(ENV), "-f", str(COMPOSE), *args], **kw)

def inspect(names):
    rows = json.loads(docker("inspect", *names).stdout)
    return {r["Name"].lstrip("/"): {"state": r["State"]["Status"], "oom": r["State"]["OOMKilled"],
            "restarts": r["RestartCount"], "started": r["State"]["StartedAt"]} for r in rows}

def available():
    return int(next(x.split()[1] for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:"))) // 1024

def health():
    t = time.monotonic()
    try:
        with urllib.request.urlopen("http://127.0.0.1:18000/healthz", timeout=3) as r:
            return {"status": r.status, "ms": round((time.monotonic() - t) * 1000, 3)}
    except Exception:
        return {"status": 0, "ms": round((time.monotonic() - t) * 1000, 3)}

def monitor():
    failures = 0
    while not stop.wait(5):
        h = health()
        failures = failures + 1 if h["status"] != 200 else 0
        sample = {"phase": phase, "t_s": round(time.monotonic() - begun), "available_mib": available(), "health": h}
        report["samples"].append(sample)
        if sample["available_mib"] < 900 or failures >= 3 or time.monotonic() - begun > 1200:
            report["abort"] = "headroom below 900 MiB, three API failures, or 20-minute deadline"
            stop.set()
        if len(report["samples"]) % 4 == 0:
            try:
                current = inspect(CORE)
                if current != report["core_before"]:
                    report["abort"] = "existing Argus service changed state/restarted"
                    stop.set()
            except Exception:
                report["abort"] = "cannot inspect existing Argus services"
                stop.set()

def lf_url():
    data = json.loads(docker("inspect", PROJECT + "-web").stdout)[0]
    ip = data["NetworkSettings"]["Networks"]["argus-v18-core"]["IPAddress"]
    return "http://" + ip + ":3000"

def api(path, payload=None, auth=False):
    headers = {"Content-Type": "application/json", "x-langfuse-ingestion-version": "4"}
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode((values["PUBLIC_KEY"] + ":" + values["SECRET_KEY"]).encode()).decode()
    req = urllib.request.Request(lf_url() + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, json.loads(r.read())

def summarize():
    for label in {s["phase"] for s in report["samples"]}:
        rows = [s for s in report["samples"] if s["phase"] == label]
        report["phases"][label] = {"samples": len(rows), "min_available_mib": min(s["available_mib"] for s in rows),
            "api_failures": sum(s["health"]["status"] != 200 for s in rows),
            "api_median_ms": round(statistics.median(s["health"]["ms"] for s in rows), 3),
            "api_max_ms": max(s["health"]["ms"] for s in rows)}

begun = time.monotonic()
created = False
env_created = False
watchdog_created = False
# Reject ownership mismatches before any setup or cleanup side effect.
if os.geteuid() != 0 or "holder=conantkd session=dc432c3ff537" not in Path("/opt/argus-v18/SESSION").read_text():
    raise SystemExit("STOP: wrong session or not root; no trial changes made")
try:
    if ENV.exists():
        raise RuntimeError("trial credential file already exists; do not overwrite")
    if available() < 4000:
        raise RuntimeError("insufficient initial memory: need at least 4000 MiB available")
    existing = set(docker("ps", "-a", "--format", "{{.Names}}").stdout.decode().splitlines())
    existing_vols = set(docker("volume", "ls", "-q").stdout.decode().splitlines())
    if existing.intersection(NAMES) or existing_vols.intersection(VOLUMES):
        raise RuntimeError("trial names already exist; do not overwrite")
    report["core_before"] = inspect(CORE)
    p = run(["bash", "/opt/argus-v18/app/ops/nonint-check.sh", "before"])
    report["noninterference_before"] = "snapshot saved"
    values = {k: secrets.token_hex(24) for k in ("PG_PASSWORD", "CH_PASSWORD", "REDIS_PASSWORD", "S3_PASSWORD", "SALT", "AUTH_SECRET", "USER_PASSWORD")}
    values["ENCRYPTION_KEY"] = secrets.token_hex(32)
    values["PUBLIC_KEY"] = "pk-lf-" + secrets.token_hex(16)
    values["SECRET_KEY"] = "sk-lf-" + secrets.token_hex(24)
    ENV.write_bytes(("\n".join(k + "=" + v for k, v in values.items()) + "\n").encode())
    env_created = True
    ENV.chmod(0o600)
    dc("config", "--quiet")
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    time.sleep(30)
    phase = "image-pull"
    original = COMPOSE.read_text()
    images = [line.strip().split("image: ", 1)[1] for line in original.splitlines() if line.strip().startswith("image:")]
    report["image_digests"] = {}
    for image in images:
        if stop.is_set():
            raise RuntimeError("aborted by monitor")
        print("PULL", image, flush=True)
        docker("pull", image, timeout=180)
        digests = json.loads(docker("image", "inspect", "--format", "{{json .RepoDigests}}", image).stdout)
        original = original.replace("image: " + image + "\n", "image: " + digests[0] + "\n")
        report["image_digests"][image] = digests[0]
    COMPOSE.write_bytes(original.encode())
    dc("config", "--quiet")
    run(["systemd-run", "--quiet", "--unit=argus-lab-lf1-watchdog", "--on-active=25m",
         "/usr/bin/docker", "compose", "--project-name", PROJECT, "--env-file", str(ENV),
         "-f", str(COMPOSE), "down", "--volumes", "--remove-orphans"])
    watchdog_created = True
    phase = "startup"
    created = True
    dc("up", "-d", "postgres", "redis", "minio", "clickhouse", timeout=90)
    dep_deadline = time.monotonic() + 150
    while time.monotonic() < dep_deadline and not stop.is_set():
        pg = docker("exec", PROJECT + "-postgres", "pg_isready", "-U", "langfuse", check=False)
        ch = docker("exec", PROJECT + "-clickhouse", "wget", "-qO-", "http://localhost:8123/ping", check=False)
        if pg.returncode == 0 and ch.returncode == 0:
            break
        time.sleep(5)
    else:
        report["trial_failure_states"] = inspect(NAMES[:4])
        raise RuntimeError("dependency readiness timeout")
    dc("up", "-d", "web", "worker", timeout=90)
    deadline = time.monotonic() + 420
    ready = False
    while time.monotonic() < deadline and not stop.is_set():
        try:
            code, _ = api("/api/public/health")
            if code == 200:
                ready = True
                break
        except Exception:
            pass
        states = inspect(NAMES)
        if any(v["oom"] or v["state"] == "exited" for v in states.values()):
            report["trial_failure_states"] = states
            raise RuntimeError("Langfuse dependency exited or was OOM-killed")
        time.sleep(10)
    report["ready"] = ready
    report["startup_elapsed_s"] = round(time.monotonic() - begun)
    print("READY", ready, "elapsed_s", report["startup_elapsed_s"], flush=True)
    if not ready:
        raise RuntimeError("not ready within bounded startup window")
    print("PHASE synthetic-ingestion", flush=True)
    phase = "synthetic-ingestion"
    accepted = 0
    trace_ids = set()
    window_start = datetime.now(timezone.utc).isoformat()
    for batch in range(6):
        if stop.is_set():
            raise RuntimeError("aborted by monitor")
        spans = []
        for i in range(10):
            trace = uuid.uuid4().hex
            trace_ids.add(trace)
            root_id = secrets.token_hex(8)
            now = time.time_ns()
            common = {"traceId": trace, "kind": 1, "startTimeUnixNano": str(now),
                      "endTimeUnixNano": str(now + 1000000),
                      "attributes": [{"key": "langfuse.observation.type", "value": {"stringValue": "span"}}]}
            spans.append({**common, "spanId": root_id, "name": "argus-synthetic-capacity"})
            spans.append({**common, "spanId": secrets.token_hex(8), "parentSpanId": root_id, "name": "synthetic-tool"})
        payload = {"resourceSpans": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "argus-capacity-trial"}}]},
                   "scopeSpans": [{"scope": {"name": "argus-capacity-trial"}, "spans": spans}]}]}
        status, response = api("/api/public/otel/v1/traces", payload, auth=True)
        if status != 200 or int(response.get("partialSuccess", {}).get("rejectedSpans", 0)):
            raise RuntimeError("synthetic OTLP ingestion rejected")
        accepted += 10
        print("SUBMITTED synthetic traces", accepted, flush=True)
        time.sleep(10)
    report["synthetic_traces_submitted"] = accepted
    deadline = time.monotonic() + 120
    retrieved = 0
    while time.monotonic() < deadline and not stop.is_set():
        try:
            params = {"limit": 100, "fromStartTime": window_start,
                      "toStartTime": datetime.now(timezone.utc).isoformat()}
            _, rows = api("/api/public/v2/observations?" + urllib.parse.urlencode(params), auth=True)
            observations = rows.get("data", [])
            cursor = rows.get("meta", {}).get("cursor")
            if cursor:
                _, more = api("/api/public/v2/observations?" + urllib.parse.urlencode({**params, "cursor": cursor}), auth=True)
                observations += more.get("data", [])
            retrieved = len({o.get("traceId") for o in observations}.intersection(trace_ids))
            report["synthetic_observations_retrieved"] = len(observations)
            if retrieved == accepted and len(observations) == accepted * 2:
                break
        except Exception:
            pass
        time.sleep(5)
    report["synthetic_traces_retrieved"] = retrieved
    phase = "steady"
    time.sleep(45)
    report["stats"] = docker("stats", "--no-stream", "--format", "{{.Name}} cpu={{.CPUPerc}} memory={{.MemUsage}}", *NAMES, *CORE).stdout.decode().splitlines()
    report["trial_before_cleanup"] = inspect(NAMES)
    report["success"] = retrieved == accepted and report.get("synthetic_observations_retrieved") == accepted * 2 and not stop.is_set() and all(v["state"] == "running" and not v["oom"] for v in report["trial_before_cleanup"].values())
except Exception as e:
    report["failure"] = type(e).__name__ + ": " + (str(e) if isinstance(e, RuntimeError) else "details suppressed")
    report["success"] = False
    if created:
        report["diagnostics"] = {}
        for service in ("web", "worker", "clickhouse"):
            p = docker("logs", "--tail", "70", PROJECT + "-" + service, check=False)
            text = (p.stdout + p.stderr).decode(errors="replace")
            for value in values.values():
                text = text.replace(value, "[redacted]")
            text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[address]", text)
            rows = json.loads(docker("inspect", PROJECT + "-" + service).stdout)
            report["diagnostics"][service] = {"exit_code": rows[0]["State"]["ExitCode"],
                "oom": rows[0]["State"]["OOMKilled"], "log_tail": text.splitlines()[-45:]}
finally:
    phase = "cleanup"
    if created:
        # Only this dedicated Compose project and its five synthetic volumes are removed.
        cleanup = dc("down", "--volumes", "--remove-orphans", timeout=90, check=False)
        report["cleanup_returncode"] = cleanup.returncode
    stop.set()
    if "thread" in globals():
        thread.join(timeout=8)
    report["core_after"] = inspect(CORE)
    report["core_unchanged"] = report.get("core_before") == report["core_after"]
    report["trial_containers_remaining"] = sorted(set(docker("ps", "-a", "--format", "{{.Names}}").stdout.decode().splitlines()).intersection(NAMES))
    report["trial_volumes_remaining"] = sorted(set(docker("volume", "ls", "-q").stdout.decode().splitlines()).intersection(VOLUMES))
    report["after_available_mib"] = available()
    report["after_health"] = health()
    nonint = run(["bash", "/opt/argus-v18/app/ops/nonint-check.sh", "after"], check=False)
    report["noninterference"] = "NO INTERFERENCE" in nonint.stdout.decode()
    report["success"] = bool(report.get("success")) and report["core_unchanged"] and report["noninterference"] and not report["trial_containers_remaining"] and not report["trial_volumes_remaining"] and report["after_health"]["status"] == 200
    summarize()
    if watchdog_created:
        run(["systemctl", "stop", "argus-lab-lf1-watchdog.timer"], check=False)
    if env_created:
        ENV.unlink(missing_ok=True)
    (ROOT / "report.json").write_bytes(json.dumps(report, indent=2).encode())
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2), flush=True)
raise SystemExit(0 if report["success"] else 1)
