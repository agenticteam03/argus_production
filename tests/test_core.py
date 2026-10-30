"""Offline tests of the two-VM v1.8 core: identity, guarded execution, classification, strategies,
runbooks loaded from argus/runbooks, run events and both output modes, boundaries."""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from argus.adapters.outbound.llm import ScriptedLLM
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.capabilities.spec import ExecutorError
from argus.domain.model import (Incident, IncidentOutcome, MetricSnapshot, RequestKind, TargetRef, TriggerKind,
                                utcnow)
from argus.infrastructure.wiring import Settings, build
from argus.ports.ports import StaleMetrics
from argus.tooling.executors import ExecutorRegistry

ROOT = Path(__file__).resolve().parents[1]
RUNBOOKS = ROOT / "argus" / "runbooks"          # the reviewed runbook library (D-002)


# --- fakes -------------------------------------------------------------------------------------
class FakeTargetAgent:
    """Answers like target-agent, per host. Records which host was called."""
    calls: list[tuple[str, str]] = []
    reads: list[tuple[str, str, tuple]] = []            # with the parameters: a log read searches one path per pattern
    data = {
        "http://argus-v18-tunnel:18701": {
            "/containers/argus-lab-worker/status": {"id": "aaa111", "state": "restarting", "health": "none", "restart_count": 7,
                                          "oom_killed": True, "exit_code": 137, "memory_limit_bytes": 67108864},
            "/containers/argus-lab-api/status": {"id": "bbb222", "state": "running", "health": "unhealthy", "restart_count": 0,
                                       "oom_killed": False, "exit_code": 0},
            "/containers/argus-lab-worker/logs": {"lines": ["worker holding 60 MiB of cached results"]},
            "/containers/argus-lab-worker/stats": {"memory_usage_bytes": 60000000, "memory_limit_bytes": 67108864},
            "/containers/argus-lab-worker/health": {"status": "none", "log": []},
        },
        "http://argus-v18-read-gateway:8700": {
            "/containers/argus-lab-worker/status": {"id": "ccc333", "state": "restarting", "health": "none", "restart_count": 9,
                                          "oom_killed": False, "exit_code": 1},
            "/containers/argus-lab-worker/logs": {"lines": ["FATAL: config file not found: /etc/worker/config.yml password=hunter2"]},
            "/containers/argus-lab-worker/stats": {"memory_usage_bytes": 9000000, "memory_limit_bytes": 67108864},
            "/containers/argus-lab-worker/health": {"status": "none", "log": []},
        },
    }

    def __init__(self, url, token, kind="docker_read"):
        self.url, self.token, self.kind = url, token, kind

    def get(self, path, params=None):
        FakeTargetAgent.calls.append((self.url, path))
        FakeTargetAgent.reads.append((self.url, path, tuple(sorted((params or {}).items()))))
        if self.kind == "host_probe":
            return {"total_mib": 5800, "available_mib": 4000, "cpu_busy_percent": 12, "load1": 0.2, "cpus": 1}
        if self.kind == "network_probe":
            return {"ok": False, "error": "ConnectionRefusedError"}
        if self.kind == "db_probe":
            return {"database": "argus-lab-db", "ok": True, "max_connections": 20, "reserved_connections": 3,
                    "usable_connections": 17, "client_connections": 2, "usage_percent": 11.8, "by_state": {"idle": 2},
                    "by_client": [], "longest_transactions": [], "lock_waits": 0, "blocked_sessions": 0}
        try:
            return self.data[self.url][path]
        except KeyError:
            raise ExecutorError("not_found", path)


class FakeMetrics:
    def __init__(self, by_target: dict[str, dict] | None = None, stale: bool = False):
        self.by_target, self.stale = by_target or {}, stale

    def snapshot(self, target, signals):
        if self.stale:
            raise StaleMetrics("no fresh samples")
        vals = self.by_target.get(str(target), {})
        return MetricSnapshot(target=target, observed_at=utcnow(), values={s: vals.get(s) for s in signals})

    def range(self, *a, **k):
        return []

    def dependency_probes(self, target):
        return {}


@pytest.fixture()
def make_app(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    FakeTargetAgent.calls, FakeTargetAgent.reads = [], []

    def _make(llm=None, metrics=None):
        reg = ExecutorRegistry()
        for k in ("docker_read", "host_probe", "network_probe", "db_probe"):
            reg.register(k, lambda url, tok, k=k: FakeTargetAgent(url, tok, k))
        reg.register("prometheus", FakeTargetAgent)
        s = Settings(config_dir=ROOT / "config", secrets_dir=tmp_path / "none", runbooks_dir=RUNBOOKS,
                     db_path=str(tmp_path / "t.db"), max_reads_per_step=2)
        return build(s, llm=llm, metrics=metrics or FakeMetrics(), executors=reg,
                     store=SqliteStore(str(tmp_path / "t.db")), require_credentials=False)
    return _make


def incident(app, target: str, request=RequestKind.report, reason="test", opened_at=None) -> Incident:
    inc = Incident(id=f"inc_{os.urandom(4).hex()}", target=TargetRef.parse(target), trigger_kind=TriggerKind.manual,
                   request_kind=request, reason=reason, principal="tester", trigger_id="t",
                   opened_at=opened_at or utcnow())
    app.store.create_incident(inc, None)
    return inc


# --- identity ------------------------------------------------------------------------------------
def test_target_ref_requires_host():
    assert str(TargetRef.parse("vm-166/container:argus-lab-worker")) == "vm-166/container:argus-lab-worker"
    with pytest.raises(ValueError):
        TargetRef.parse("container:argus-lab-worker")
    assert TargetRef.parse("vm-166/container:argus-lab-worker") != TargetRef.parse("vm-095/container:argus-lab-worker")


# --- classification and strategies ------------------------------------------------------------------
def test_healthy_check_ends_without_model(make_app):
    llm = ScriptedLLM([])
    app = make_app(llm=llm, metrics=FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 0}}))
    inc = app.runner.run(incident(app, "vm-166/container:argus-lab-worker", RequestKind.check).id)
    assert inc.outcome == IncidentOutcome.no_incident and llm.calls == 0


def test_unsupported_report_runs_evidence_pack_without_model(make_app):
    llm = ScriptedLLM([])
    app = make_app(llm=llm, metrics=FakeMetrics({"vm-095/container:argus-lab-worker": {"restarts_10m": 0}}))
    inc = app.runner.run(incident(app, "vm-095/container:argus-lab-worker").id)
    assert inc.outcome == IncidentOutcome.unsupported_escalated and llm.calls == 0
    ev = app.store.list_evidence(inc.id)
    assert any(e.capability == "container.status" for e in ev)
    assert all(e.host == "vm-095" for e in ev if e.capability)          # never another host
    assert all(len(e.sha256) == 64 for e in ev)


def test_stale_metrics_undiagnosable_without_model(make_app):
    llm = ScriptedLLM([])
    app = make_app(llm=llm, metrics=FakeMetrics(stale=True))
    inc = app.runner.run(incident(app, "vm-166/container:argus-lab-worker").id)
    assert inc.outcome == IncidentOutcome.undiagnosable and llm.calls == 0
    assert any("RB-014" in f for f in inc.findings)


def test_same_name_two_hosts_two_diagnoses(make_app):
    def script(ctx: str):
        host = "vm-166" if "target: vm-166/" in ctx else "vm-095"
        t = f"{host}/container:argus-lab-worker"
        if "container.status" not in ctx:
            return {"calls": [("get_container_status", {"target": t}), ("get_container_logs", {"target": t, "tail": 20})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        diag = "OOM-killed by its 64 MiB limit" if host == "vm-166" else "non-OOM crash: missing config file"
        return {"calls": [("conclude", {"diagnosis": diag, "evidence_ids": ids[-2:], "confidence": "high",
                                        "root_cause_target": t})]}
    llm = ScriptedLLM(script)
    metrics = FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137},
                           "vm-095/container:argus-lab-worker": {"restarts_10m": 6, "oom_killed": 0, "last_exit_code": 1}})
    app = make_app(llm=llm, metrics=metrics)
    a = app.runner.run(incident(app, "vm-166/container:argus-lab-worker").id)
    b = app.runner.run(incident(app, "vm-095/container:argus-lab-worker").id)
    assert a.outcome == b.outcome == IncidentOutcome.diagnosed
    assert a.incident_class == b.incident_class == "container_restart_loop"
    assert "OOM" in a.diagnosis and "config" in b.diagnosis
    assert a.root_cause_target == "vm-166/container:argus-lab-worker" and b.root_cause_target == "vm-095/container:argus-lab-worker"
    urls = {u for u, _ in FakeTargetAgent.calls}
    assert "http://argus-v18-tunnel:18701" in urls and "http://argus-v18-read-gateway:8700" in urls
    logs = [e for e in app.store.list_evidence(b.id) if e.capability == "container.logs"][0]
    assert "hunter2" not in logs.model_dump_json() and logs.redactions >= 1


def test_out_of_scope_and_fabricated_tools_are_refused(make_app):
    replies = [
        {"calls": [("get_container_status", {"target": "vm-095/container:argus-lab-worker"})]},   # other host: not offered
        {"calls": [("restart_container", {"target": "vm-166/container:argus-lab-worker"})]},     # write name: fabricated
        {"calls": [("escalate", {"reason": "cannot proceed"})]},
    ]
    llm = ScriptedLLM(replies)
    metrics = FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}})
    app = make_app(llm=llm, metrics=metrics)
    inc = app.runner.run(incident(app, "vm-166/container:argus-lab-worker").id)
    assert inc.outcome == IncidentOutcome.no_action_escalated
    events = [a.event for a in app.store.list_for(inc.id)]
    assert "decision.invalid" in events and "security.fabricated_tool" in events
    assert not any("argus-v18-read-gateway" in u for u, _ in FakeTargetAgent.calls)


def test_invoke_refuses_cross_host_read_directly(make_app):
    from argus.application.invoke_capability import InvocationContext
    app = make_app()
    inc = incident(app, "vm-166/container:argus-lab-worker")
    ctx = InvocationContext(incident=inc, caller="test", scope=app.runner.scope(inc.target))
    obs, ref = app.runner.invoke(ctx, "container.status", {"target": "vm-095/container:argus-lab-worker"})
    assert obs.status == "refused" and obs.error_category == "out_of_scope" and ref is not None
    obs2, _ = app.runner.invoke(ctx, "container.status", {"target": "container:argus-lab-worker"})
    assert obs2.status == "refused" and obs2.error_category == "invalid_args"
    assert FakeTargetAgent.calls == []


def test_dependency_scope_allows_neighbour(make_app):
    app = make_app()
    scope = {str(t) for t in app.runner.scope(TargetRef.parse("vm-166/container:argus-lab-api"))}
    # argus-lab-client declares depends_on argus-lab-api (ACR-0035, S2-5), so the dependent is in the API's scope too
    assert scope == {"vm-166/container:argus-lab-api", "vm-166/container:argus-lab-cache",
                     "vm-166/container:argus-lab-client", "vm-166/host:vm-166"}


def test_evidence_is_insert_only(make_app):
    import sqlite3
    app = make_app()
    app.runner.run(incident(app, "vm-095/container:argus-lab-worker").id)
    with pytest.raises(sqlite3.DatabaseError):
        app.store._q("UPDATE evidence SET sha256='x'")


# --- boundaries (v1.8 §2.3) ------------------------------------------------------------------------
def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
        elif isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
    return out


@pytest.mark.parametrize("pkg,forbidden", [
    ("domain", ("argus.", "fastapi", "httpx", "sqlite3")),
    ("detectors", ("argus.application", "argus.adapters", "argus.tooling", "httpx")),
    ("policy", ("argus.application", "argus.adapters", "argus.tooling", "argus.capabilities")),
    ("application", ("fastapi", "argus.adapters", "argus.tooling", "argus.capabilities", "langgraph")),
])
def test_import_boundaries(pkg, forbidden):
    for f in (ROOT / "argus" / pkg).glob("*.py"):
        for mod in _imports(f):
            if pkg == "domain" and mod.startswith("argus.domain"):
                continue
            assert not any(mod.startswith(x) for x in forbidden), f"{f.name} imports {mod}"


def test_only_invoke_capability_calls_the_catalogue():
    offenders = []
    for f in (ROOT / "argus").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        if "catalogue.call(" in text and f.name != "invoke_capability.py":
            offenders.append(f.name)
    assert offenders == []


# --- HTTP: JWT, roles, webhook token ----------------------------------------------------------------
def test_http_auth_and_webhook(make_app):
    from fastapi.testclient import TestClient
    from pwdlib import PasswordHash
    from argus.adapters.inbound.http import build_api, build_webhook
    app = make_app()
    app.alertmanager_token = "am-token-123"
    app.store.upsert_principal("alice", "human", "operator", ["lab"], PasswordHash.recommended().hash("a-long-password"))
    app.store.upsert_principal("vera", "human", "viewer", ["lab"], PasswordHash.recommended().hash("a-long-password"))
    api, hook = TestClient(build_api(app)), TestClient(build_webhook(app))
    assert api.post("/api/v1/auth/token", data={"username": "alice", "password": "wrong"}).status_code == 401
    tok = api.post("/api/v1/auth/token", data={"username": "alice", "password": "a-long-password"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = api.post("/api/v1/investigations", headers=h, json={"target": "vm-166/container:argus-lab-worker", "reason": "x",
                                                            "idempotency_key": "k1"})
    assert r.status_code == 202 and not r.json()["duplicate"]
    assert api.post("/api/v1/investigations", headers=h, json={"target": "vm-166/container:argus-lab-worker",
                                                               "idempotency_key": "k1"}).json()["duplicate"]
    assert api.post("/api/v1/investigations", headers=h, json={"target": "container:argus-lab-worker"}).status_code == 422
    vt = api.post("/api/v1/auth/token", data={"username": "vera", "password": "a-long-password"}).json()["access_token"]
    assert api.post("/api/v1/investigations", headers={"Authorization": f"Bearer {vt}"},
                    json={"target": "vm-166/container:argus-lab-worker"}).status_code == 403
    app.store.set_disabled("alice", True)
    assert api.get("/api/v1/incidents", headers=h).status_code == 401
    alert = {"alerts": [{"status": "firing", "fingerprint": "f1", "startsAt": "2026-10-08T12:00:00Z",
                         "labels": {"alertname": "ContainerRestartLoop", "argus_host": "vm-095",
                                    "container": "argus-lab-api"}}]}
    assert hook.post("/api/v1/alerts", json=alert).status_code == 401
    ok = hook.post("/api/v1/alerts", json=alert, headers={"Authorization": "Bearer am-token-123"}).json()
    assert len(ok["accepted"]) == 1
    assert hook.get("/docs").status_code == 404          # no Swagger on the private listener



# --- run events and the two output modes ------------------------------------------------------------
def _nodes(app, iid):
    seen = []
    for e in app.store.list_run_events(iid):
        if not seen or seen[-1] != e["node"]:
            seen.append(e["node"])
    return seen


def test_run_events_follow_the_real_v18_nodes(make_app):
    def script(ctx):
        t = "vm-166/container:argus-lab-worker"
        if "container.status" not in ctx:
            return {"calls": [("get_container_status", {"target": t})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "OOM-killed by its 64 MiB limit", "evidence_ids": ids[-1:], "confidence": "high",
                                        "root_cause_target": t})]}
    m = FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137},
                     "vm-095/container:argus-lab-worker": {"restarts_10m": 0}})
    app = make_app(llm=ScriptedLLM(script), metrics=m)
    diag = app.runner.run(incident(app, "vm-166/container:argus-lab-worker").id)
    assert _nodes(app, diag.id) == ["detect", "recall", "investigate", "act", "investigate", "record"]
    healthy = app.runner.run(incident(app, "vm-095/container:argus-lab-worker", RequestKind.check).id)
    assert _nodes(app, healthy.id) == ["detect", "record"]
    unsupported = app.runner.run(incident(app, "vm-095/container:argus-lab-worker").id)
    assert _nodes(app, unsupported.id) == ["detect", "evidence_pack", "record"]
    evs = app.store.list_run_events(diag.id)
    acts = [e for e in evs if e["node"] == "act" and e["phase"] == "step"]
    assert acts and all(e["data"]["host"] == "vm-166" and e["data"]["sha256"] for e in acts)
    rec = [e for e in evs if e["node"] == "recall"][-1]["data"]
    assert rec["passages"] and all(p["runbook_id"].startswith("RB-") and len(p["sha256"]) == 64 for p in rec["passages"])
    decided = [e["data"]["decided_by"] for e in evs if e["node"] == "investigate" and e["phase"] == "exit"]
    assert decided == ["model", "model"]
    audit = [a.event for a in app.store.list_for(diag.id)]
    assert "recall.passages" in audit


def test_formatted_and_raw_views_render_the_same_run(make_app):
    import json as _json
    from argus.adapters.inbound.cli.render import Formatter, raw_event
    app = make_app(metrics=FakeMetrics({"vm-095/container:argus-lab-worker": {"restarts_10m": 0}}))
    inc = app.runner.run(incident(app, "vm-095/container:argus-lab-worker").id)
    events = app.store.list_run_events(inc.id)
    fmt = Formatter(color=False, width=100)
    text = "\n".join(line for ev in events for line in fmt.event(ev))
    assert text.index("▌ DETECT") < text.index("▌ EVIDENCE_PACK") < text.index("▌ RECORD")
    assert "UNSUPPORTED" in text and "vm-095" in text and "OBSERVE" not in text
    raw = [raw_event(ev) for ev in events]
    assert len(raw) == len(events) and all(_json.loads(r)["node"] for r in raw)


def test_formatted_act_line_shows_the_whole_result_on_a_narrow_terminal():
    """The SC-07 class demo (2026-10-07) printed `vm-166/container:arg`: the result was cut to fit one line. The result
    now wraps under the tool line (at most 4 lines, then an ellipsis) and no line is wider than the terminal."""
    from argus.adapters.inbound.cli.render import Formatter
    result = ("vm-166/container:argus-lab-backend: running, health healthy, restarts=0, exit=0, oom_killed=false, "
              "networks=argus-lab-iso")
    ev = {"node": "act", "phase": "step", "data": {"executor": "docker_read", "host": "vm-166",
                                                    "tool": "get_container_status", "status": "ok", "result": result}}
    lines = Formatter(color=False, width=64).event(ev)
    text = " ".join(ln.strip() for ln in lines)
    tool = [ln for ln in lines if "get_container_status" in ln]
    assert len(tool) == 1 and "✓" in tool[0]
    assert "networks=argus-lab-iso" in text and "health healthy" in text
    assert all(len(ln) <= 64 for ln in lines)
    long = Formatter(color=False, width=64).event({**ev, "data": {**ev["data"], "result": "x " * 400}})
    assert len(long) <= 2 + 1 + 4 and long[-1].rstrip().endswith("…")       # header (2) + tool line + 4


def test_runbooks_are_loaded_with_versions(make_app):
    app = make_app()
    kb = app.runner.knowledge
    assert {"RB-001", "RB-002", "RB-003", "RB-008"} <= kb.ids
    assert "Safety and approval contract" in kb.pinned_text



def test_answer_from_another_host_is_never_attributed(make_app):
    from argus.application.invoke_capability import InvocationContext
    app = make_app()
    FakeTargetAgent.data["http://argus-v18-tunnel:18701"]["/containers/argus-lab-api/status"] = {
        "id": "zzz", "state": "running", "host": "vm-095"}          # misrouted answer
    inc = incident(app, "vm-166/container:argus-lab-api")
    ctx = InvocationContext(incident=inc, caller="test", scope=app.runner.scope(inc.target))
    obs, ref = app.runner.invoke(ctx, "container.status", {"target": "vm-166/container:argus-lab-api"})
    assert obs.status == "error" and "ATTRIBUTION MISMATCH" in obs.model_text



def test_deployable_files_have_unix_line_endings():
    """Files shipped to the Linux VMs must not contain CRLF (bash fails on it)."""
    bad = []
    for pattern in ("ops/*.sh", "ops/*.py", "deploy/**/*", "services/**/*", "config/*", "Dockerfile", "argus/**/*.py"):
        for f in ROOT.glob(pattern):
            if f.is_file() and "__pycache__" not in f.parts and b"\r\n" in f.read_bytes():
                bad.append(str(f.relative_to(ROOT)))
    assert bad == [], bad


def test_runbook_library_lives_in_the_repository(monkeypatch):
    """D-002: the reviewed runbook library is part of this repository (architecture 2.4) and the default location."""
    from argus.adapters.outbound.config_adapters import TfidfRunbooks
    monkeypatch.delenv("ARGUS_RUNBOOKS_DIR", raising=False)
    lib = ROOT / "argus" / "runbooks"
    assert Settings().runbooks_dir.resolve() == lib.resolve()
    kb = TfidfRunbooks(str(lib))
    assert len(kb.ids) == 23
    assert kb.library_version and kb.pinned_text            # index and conventions found next to the runbooks
    assert "/opt/argus-runbooks" not in (ROOT / "deploy" / "vm-095" / "compose.core.yml").read_text(encoding="utf-8")
    assert not (ROOT / "config" / "runbooks.lock").exists()



def test_responses_adapter_parses_function_calls_text_and_usage():
    """GPT-5.x: tools go through /v1/responses; the adapter maps its output items onto ModelReply."""
    from types import SimpleNamespace as N
    from argus.adapters.outbound.llm import OpenAIResponses
    r = N(status="completed", usage=N(input_tokens=11, output_tokens=7), output=[
        N(type="reasoning"),
        N(type="message", content=[N(type="output_text", text="checking memory")]),
        N(type="function_call", name="container_status", arguments='{"target": "vm-166/container:x"}')])
    rep = OpenAIResponses.parse(r)
    assert rep.finish_reason == "tool_calls" and rep.tool_calls[0].name == "container_status"
    assert rep.text == "checking memory" and rep.usage.input_tokens == 11
    assert OpenAIResponses.parse(N(status="incomplete", incomplete_details=N(reason="max_output_tokens"),
                                   output=[], usage=None)).finish_reason == "length"


def test_provider_error_escalates_at_once(make_app):
    class Down:
        calls = 0

        def decide(self, messages, tools):
            Down.calls += 1
            raise RuntimeError("400 tools not supported")
    metrics = FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}})
    app = make_app(llm=Down(), metrics=metrics)
    inc = app.runner.run(incident(app, "vm-166/container:argus-lab-worker").id)
    assert inc.outcome == IncidentOutcome.no_action_escalated and Down.calls == 1
    assert "provider failed at step 1" in inc.diagnosis


def test_permanent_provider_error_is_not_retried():
    from argus.adapters.outbound.llm import _with_retry

    class Bad(Exception):
        status_code = 400
    calls = []

    def call():
        calls.append(1)
        raise Bad("bad request")
    try:
        _with_retry(call, 2)
    except Bad:
        pass
    assert len(calls) == 1


def test_conclude_with_empty_diagnosis_is_rejected(make_app):
    """SC-03 on the VMs: the model concluded with diagnosis="" and it was recorded. It must be corrected instead."""
    def script(ctx: str):
        t = "vm-166/container:argus-lab-worker"
        if "container.status" not in ctx:
            return {"calls": [("get_container_status", {"target": t})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        diag = "OOM-killed by its own 64 MiB limit" if "diagnosis text is required" in ctx else ""
        return {"calls": [("conclude", {"diagnosis": diag, "evidence_ids": ids[-1:], "confidence": "high"})]}
    metrics = FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}})
    app = make_app(llm=ScriptedLLM(script), metrics=metrics)
    inc = app.runner.run(incident(app, "vm-166/container:argus-lab-worker").id)
    assert inc.outcome == IncidentOutcome.diagnosed and inc.diagnosis.startswith("OOM-killed")


def test_exporter_last_exit_survives_the_restart(tmp_path, monkeypatch):
    """Docker resets State.ExitCode/OOMKilled once a restarted container runs; the exporter reads the last `die`."""
    import importlib.util
    cfg = tmp_path / "target.json"
    cfg.write_bytes(b'{"host": "vm-166", "containers": ["argus-lab-worker"]}')
    monkeypatch.setenv("ROLE", "exporter")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    spec = importlib.util.spec_from_file_location("ta_service", ROOT / "services" / "target" / "service.py")
    svc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(svc)
    running = {"running": True, "exit_code": 0, "oom_killed": False}
    evs = [{"action": "start", "exit_code": None}, {"action": "oom", "exit_code": None},
           {"action": "die", "exit_code": "137"}, {"action": "start", "exit_code": None}]
    assert svc.last_exit(running, evs) == (137, True)
    crash = [{"action": "oom", "exit_code": None}, {"action": "die", "exit_code": "137"},
             {"action": "start", "exit_code": None}, {"action": "die", "exit_code": "1"}]
    assert svc.last_exit(running, crash) == (1, False)             # an older OOM does not leak into the last exit
    assert svc.last_exit({"running": False, "exit_code": 1, "oom_killed": False}, evs) == (1, False)
    assert svc.last_exit(running, []) == (0, False)


def test_stopped_exporter_is_a_blind_spot_not_healthy(monkeypatch):
    """SC-10 on the VMs: with the exporter stopped, restarts_10m still answered 0 from older samples and a check said
    healthy. The scrape gate (`_scrape_up`) must make the host undiagnosable instead."""
    import yaml
    from argus.adapters.outbound import config_adapters as ca

    class Resp:
        def __init__(self, result):
            self.result = result

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"result": self.result}}
    queries = []

    def fake_get(url, params, timeout):
        queries.append(params["query"])
        if params["query"].startswith("up{"):
            return Resp([{"value": [1e12, "0"]}])                 # the scrape is failing
        return Resp([{"value": [1e12, "0"]}])                     # a range function still answers "0"
    monkeypatch.setattr(ca.httpx, "get", fake_get)
    signals = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
    inv = type("Inv", (), {"host": lambda self, h: type("H", (), {"executors": {"prometheus": "http://p:9090"}})()})()
    m = ca.PrometheusMetrics(inv, signals)
    with pytest.raises(StaleMetrics, match="blind spot"):
        m.snapshot(TargetRef.parse("vm-095/container:argus-lab-api"), {"restarts_10m"})
    assert queries == ['up{argus_host="vm-095",job="argus-v18-exporter"}']


def test_unreachable_executor_is_flagged_to_the_model(make_app, monkeypatch):
    """SC-12 on the VMs: the model retried a dead read gateway for 7 steps. Once an executor is unreachable, the
    context says so, so the model stops calling it."""
    seen = []

    def script(ctx: str):
        seen.append(ctx)
        t = "vm-166/container:argus-lab-worker"
        if "UNAVAILABLE: executor docker_read@vm-166" in ctx:
            return {"calls": [("escalate", {"reason": "docker reads on vm-166 are unreachable"})]}
        return {"calls": [("get_container_status", {"target": t})]}

    def dead(self, path, params=None):
        raise ExecutorError("unreachable", f"{self.url}{path}: ConnectError")
    monkeypatch.setattr(FakeTargetAgent, "get", dead)
    metrics = FakeMetrics({"vm-166/container:argus-lab-worker": {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}})
    app = make_app(llm=ScriptedLLM(script), metrics=metrics)
    inc = app.runner.run(incident(app, "vm-166/container:argus-lab-worker").id)
    assert inc.outcome == IncidentOutcome.no_action_escalated and len(seen) == 2
