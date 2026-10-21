"""T-0015 step 5: the UI contract (ACR-0001). `contracts/ui-api.json` is the OpenAPI schema of exactly the routes a
user interface may rely on; `contracts/samples/*.json` are real responses from a scripted SC-03-like run, which the
frontend's tests use as their fake API. A change to the API that would break a frontend turns this test red.

Updating the contract is a deliberate, reviewed act:
    ARGUS_UPDATE_UI_CONTRACT=1 python -m pytest tests/test_ui_contract.py
then review the diff of contracts/ in the pull request."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.outbound.llm import ScriptedLLM
from test_core import FakeMetrics, make_app  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "ui-api.json"
SAMPLES = ROOT / "contracts" / "samples"
UPDATE = os.getenv("ARGUS_UPDATE_UI_CONTRACT") == "1"

# (method, path) a UI may call - docs/API-FOR-UI.md describes each one
UI_ROUTES = [("post", "/api/v1/auth/token"), ("post", "/api/v1/auth/logout"), ("get", "/api/v1/me"), ("get", "/api/v1/incidents"),
             ("get", "/api/v1/incidents/{incident_id}"), ("get", "/api/v1/incidents/{incident_id}/events"),
             ("get", "/api/v1/evidence/{evidence_id}"), ("get", "/api/v1/escalations"),
             ("post", "/api/v1/investigations"), ("get", "/api/v1/targets"),
             ("get", "/api/v1/host-metrics"), ("get", "/api/v1/incidents/{incident_id}/metrics"),
             ("get", "/api/v1/topology"), ("get", "/api/v1/target-metrics"),
             ("get", "/api/v1/overview")]
PASSWORD = "a-long-password"
SC03 = "vm-166/container:argus-lab-worker"          # OOM restart loop, diagnosed
UNSUPPORTED = "vm-095/container:argus-lab-worker"   # healthy metrics + report -> unsupported, escalated


def ui_schema(openapi: dict) -> dict:
    """The part of the OpenAPI document a UI depends on: its routes and every schema they reference."""
    paths: dict = {}
    for method, path in UI_ROUTES:
        paths.setdefault(path, {})[method] = openapi["paths"][path][method]
    all_schemas = openapi.get("components", {}).get("schemas", {})
    needed: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref", "")
            if ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[1]
                if name not in needed:
                    needed.add(name)
                    walk(all_schemas[name])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(paths)
    out = {"openapi": openapi["openapi"], "info": {"title": "Argus API for user interfaces",
                                                   "version": openapi["info"]["version"]}, "paths": paths}
    if needed:
        out["components"] = {"schemas": {n: all_schemas[n] for n in sorted(needed)}}
    if "securitySchemes" in openapi.get("components", {}):
        out.setdefault("components", {})["securitySchemes"] = openapi["components"]["securitySchemes"]
    return out


def shape(value):
    """The structure of a response (keys and value types), not its values: ids and times change on every run."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


def scripted_run(make_app) -> dict[str, object]:
    """One SC-03-like diagnosis and one unsupported report, then every UI read with a read-only token."""
    from argus.adapters.inbound.http import build_api

    def script(ctx):
        if "container.status" not in ctx:
            return {"calls": [("get_container_status", {"target": SC03}),
                              ("get_container_logs", {"target": SC03, "tail": 20})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "OOM-killed by its 64 MiB memory limit", "evidence_ids": ids[-2:],
                                        "confidence": "high", "root_cause_target": SC03})]}
    metrics = FakeMetrics({SC03: {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137},
                           UNSUPPORTED: {"restarts_10m": 0},
                           "vm-095/host:vm-095": {"host_cpu_busy_ratio": 0.25,
                                                   "host_memory_available_ratio": 0.4,
                                                   "host_disk_used_ratio": 0.7},
                           "vm-166/host:vm-166": {"host_cpu_busy_ratio": 0.8,
                                                   "host_memory_available_ratio": 0.4,
                                                   "host_disk_used_ratio": 0.9}})
    app = make_app(llm=ScriptedLLM(script), metrics=metrics)
    app.store.upsert_principal("alice", "human", "operator", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = TestClient(build_api(app))
    full = api.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD}).json()["access_token"]
    started = {}
    for target in (SC03, UNSUPPORTED):
        r = api.post("/api/v1/investigations", headers={"Authorization": f"Bearer {full}"},
                     json={"target": target, "reason": "UI contract sample"})
        started[target] = r.json()["incident_id"]
        app.runner.run(started[target])
    login = api.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD, "scope": "read"})
    read = {"Authorization": f"Bearer {login.json()['access_token']}"}
    inc = started[SC03]
    detail = api.get(f"/api/v1/incidents/{inc}", headers=read).json()
    out = {"login": login.json(), "me": api.get("/api/v1/me", headers=read).json(),
           "incidents": api.get("/api/v1/incidents", headers=read).json(), "incident": detail,
           "events": api.get(f"/api/v1/incidents/{inc}/events", headers=read).json(),
           "evidence": api.get(f"/api/v1/evidence/{detail['evidence'][0]['evidence_id']}", headers=read).json(),
           "escalations": api.get("/api/v1/escalations", headers=read).json(),
           "targets": api.get("/api/v1/targets", headers=read).json(),
           "host-metrics": api.get("/api/v1/host-metrics", headers=read).json(),
           "incident-metrics": api.get(f"/api/v1/incidents/{inc}/metrics", headers=read).json(),   # ACR-0017
           "topology": api.get("/api/v1/topology", headers=read).json(),
           "topology-incident": api.get("/api/v1/topology", params={"incident_id": inc}, headers=read).json(),
           "target-metrics": api.get("/api/v1/target-metrics", params={"target": SC03, "range": "15m"},   # ACR-0021
                                     headers=read).json(),
           "overview": api.get("/api/v1/overview", headers=read).json()}                     # ACR-0021
    # ACR-0012: what the UI does with an investigate token (after the others, so they keep their content)
    inv = api.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD, "scope": "investigate"})
    out["investigation"] = api.post("/api/v1/investigations", json={"target": SC03, "reason": "from the UI",
                                                                    "request_kind": "check"},
                                    headers={"Authorization": f"Bearer {inv.json()['access_token']}"}).json()
    out["login"]["access_token"] = "<a JWT>"          # a sample must never hold a usable token
    return out


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


def test_the_api_matches_the_ui_contract(make_app):
    from argus.adapters.inbound.http import build_api
    current = ui_schema(build_api(make_app()).openapi())
    if UPDATE:
        _write(CONTRACT, current)
    assert CONTRACT.exists(), "contracts/ui-api.json is missing (see this file's docstring)"
    assert json.loads(CONTRACT.read_text(encoding="utf-8")) == json.loads(json.dumps(current, default=str)), (
        "the API changed for user interfaces: if intended, regenerate contracts/ (see this file's docstring)")


def test_sample_responses_keep_their_shape(make_app):
    run = scripted_run(make_app)
    changed = []
    for name, body in run.items():
        path = SAMPLES / f"{name}.json"
        if UPDATE:
            _write(path, body)
        if not path.exists():
            changed.append(f"{name}.json missing")
        elif shape(json.loads(path.read_text(encoding="utf-8"))) != shape(json.loads(json.dumps(body, default=str))):
            changed.append(f"{name}.json changed shape")
    assert not changed, f"{changed}: if intended, regenerate contracts/ (see this file's docstring)"


def test_samples_cover_a_diagnosis_and_an_escalation(make_app):
    run = scripted_run(make_app)
    assert run["me"]["access"] == "read" and "start_investigation" not in run["me"]["actions"]
    assert run["incident"]["outcome"] == "diagnosed" and run["incident"]["evidence"]
    assert {e["node"] for e in run["events"]} >= {"detect", "investigate", "act", "record"}
    assert run["escalations"], "the unsupported report must leave an escalation"
    assert run["login"]["access_token"] == "<a JWT>"
