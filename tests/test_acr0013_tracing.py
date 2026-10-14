"""ACR-0013 (LF-2), part A: optional, filtered OTLP tracing of the worker's investigations for Langfuse.

- Off by default: the runner's event sink stays the store.
- One root trace per execution attempt (attributes: incident id, class, strategy, outcome, attempt); child spans per
  graph node, and per capability read inside `act`. A resumed attempt is a new root with the same incident id.
- An allowlist of attributes: never prompts, replies, tool arguments or results, evidence bodies, signals' values,
  runbook passages, targets' addresses or secrets.
- Fail-open: an exporter that fails, or a full queue, drops telemetry and counts it; the investigation, its run
  events and the audit are unaffected. The queue is bounded and never blocks the graph.
- The OTLP/HTTP JSON body and Langfuse's headers (Basic auth from the project key pair, ingestion version 4); a
  shutdown flush bounded by a timeout.
"""
from __future__ import annotations

import base64
import json
import threading
import time

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome
from test_core import FakeMetrics, incident, make_app  # noqa: F401  (fixture)

WORKER = "vm-166/container:argus-lab-worker"


def oom_script(ctx: str):
    if "container.status" not in ctx:
        return {"calls": [("get_container_status", {"target": WORKER}), ("get_container_logs", {"target": WORKER, "tail": 20})]}
    ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
    return {"calls": [("conclude", {"diagnosis": "OOM-killed by its 64 MiB limit (password=hunter2)", "evidence_ids": ids[-2:],
                                    "confidence": "high", "root_cause_target": WORKER})]}


class Capture:
    """A fake OTLP endpoint: records each POST (url, headers, body); can fail on purpose."""

    def __init__(self, fail: bool = False, delay: float = 0.0):
        self.posts, self.fail, self.delay = [], fail, delay

    def __call__(self, url, headers, body, timeout):
        time.sleep(self.delay)
        if self.fail:
            raise OSError("langfuse unreachable")
        self.posts.append((url, headers, json.loads(body)))

    def spans(self):
        return [s for _, _, b in self.posts for rs in b["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]


def attrs(span):
    out = {}
    for kv in span["attributes"]:
        v = kv["value"]
        out[kv["key"]] = next(iter(v.values()))
    return out


def traced_app(make_app, capture, **kw):
    from argus.observability.tracing import OtlpExporter, TracingEventSink
    app = make_app(llm=ScriptedLLM(oom_script),
                   metrics=FakeMetrics({WORKER: {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}}))
    exporter = OtlpExporter("http://langfuse-web:3000/api/public/otel/v1/traces", "pk-lf-test", "sk-lf-test",
                            post=capture, **kw)
    app.runner.events = TracingEventSink(app.runner.events, exporter)
    return app, exporter


# --- off by default --------------------------------------------------------------------------------------------------
def test_tracing_is_off_by_default(make_app):
    from argus.observability.tracing import TracingEventSink
    app = make_app()
    assert app.settings.tracing_enabled is False
    assert not isinstance(app.runner.events, TracingEventSink)


# --- the spans ---------------------------------------------------------------------------------------------------------
def test_one_root_per_attempt_and_correlated_children(make_app):
    cap = Capture()
    app, exporter = traced_app(make_app, cap)
    inc = app.runner.run(incident(app, WORKER).id)
    exporter.close(timeout=5)
    assert inc.outcome == IncidentOutcome.diagnosed
    spans = cap.spans()
    roots = [s for s in spans if not s.get("parentSpanId")]
    assert len(roots) == 1
    root = roots[0]
    a = attrs(root)
    assert a["argus.incident_id"] == inc.id and a["argus.incident_class"] == "container_restart_loop"
    assert a["argus.outcome"] == "diagnosed" and a["argus.strategy"] and a["argus.attempt"]
    assert {s["traceId"] for s in spans} == {root["traceId"]} and len(root["traceId"]) == 32
    names = [s["name"] for s in spans]
    assert {"detect", "recall", "investigate", "act"} <= set(names)
    reads = [attrs(s) for s in spans if s["name"] == "capability"]
    assert {r["argus.capability"] for r in reads} >= {"container.status", "container.logs"}
    assert all(s["endTimeUnixNano"] >= s["startTimeUnixNano"] for s in spans)


def test_a_resumed_attempt_is_a_new_root_with_the_same_incident(make_app):
    from argus.observability.tracing import TracingEventSink
    cap = Capture()
    app, exporter = traced_app(make_app, cap)
    sink = app.runner.events
    inc = incident(app, WORKER)
    sink.append_run_event(inc.id, "detect", "enter", {"target": WORKER})        # an attempt that dies here
    app.runner.events = TracingEventSink(sink.inner, exporter)                   # a new worker process takes it over
    app.runner.run(inc.id)
    sink.end_open_attempts("worker stopped")                                     # the dead attempt is closed as such
    exporter.close(timeout=5)
    roots = [attrs(s) for s in cap.spans() if not s.get("parentSpanId")]
    assert len(roots) == 2 and {r["argus.incident_id"] for r in roots} == {inc.id}
    assert len({r["argus.attempt"] for r in roots}) == 2


# --- the allowlist -----------------------------------------------------------------------------------------------------
def test_nothing_sensitive_is_exported(make_app):
    cap = Capture()
    app, exporter = traced_app(make_app, cap)
    app.runner.run(incident(app, WORKER).id)
    exporter.close(timeout=5)
    body = json.dumps([b for _, _, b in cap.posts])
    for secret_or_content in ("hunter2", "OOM-killed by its 64 MiB", "argus-v18-tunnel", "18701", "restarts_10m",
                              "tail", "passages", "diagnosis", "signals"):
        assert secret_or_content not in body, secret_or_content
    allowed = {"argus.incident_id", "argus.incident_class", "argus.strategy", "argus.outcome", "argus.attempt",
               "argus.node", "argus.capability", "argus.status", "argus.error_category", "argus.step",
               "argus.decided_by", "argus.evidence_id", "argus.host", "argus.target_kind", "langfuse.trace.name",
               "langfuse.observation.type"}
    assert {k for s in cap.spans() for k in attrs(s)} <= allowed


# --- fail-open and bounded -------------------------------------------------------------------------------------------
def test_an_unreachable_langfuse_drops_telemetry_and_nothing_else(make_app):
    cap = Capture(fail=True)
    app, exporter = traced_app(make_app, cap)
    inc = app.runner.run(incident(app, WORKER).id)
    exporter.close(timeout=5)
    assert inc.outcome == IncidentOutcome.diagnosed
    assert app.store.list_for(inc.id), "the audit is written"
    assert app.store.list_run_events(inc.id) if hasattr(app.store, "list_run_events") else True
    assert exporter.dropped > 0 and exporter.exported == 0


def test_a_full_queue_drops_without_blocking(make_app):
    from argus.observability.tracing import OtlpExporter
    slow = Capture(delay=0.5)
    exporter = OtlpExporter("http://x/api/public/otel/v1/traces", "pk", "sk", post=slow, max_queue=3, batch_size=1)
    t0 = time.monotonic()
    for i in range(50):
        exporter.submit({"name": f"s{i}"})
    assert time.monotonic() - t0 < 0.2                 # the caller never waits for Langfuse
    assert exporter.dropped >= 40
    exporter.close(timeout=0.1)


# --- the wire format ---------------------------------------------------------------------------------------------------
def test_the_otlp_body_and_langfuse_headers(make_app):
    cap = Capture()
    app, exporter = traced_app(make_app, cap)
    app.runner.run(incident(app, WORKER).id)
    exporter.close(timeout=5)
    url, headers, body = cap.posts[0]
    assert url.endswith("/api/public/otel/v1/traces")
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"pk-lf-test:sk-lf-test").decode()
    assert headers["x-langfuse-ingestion-version"] == "4" and headers["Content-Type"] == "application/json"
    rs = body["resourceSpans"][0]
    assert {"key": "service.name", "value": {"stringValue": "argus-worker"}} in rs["resource"]["attributes"]
    assert rs["scopeSpans"][0]["scope"]["name"] == "argus"
    assert all(len(s["spanId"]) == 16 for s in cap.spans())


def test_close_flushes_within_its_timeout(make_app):
    from argus.observability.tracing import OtlpExporter
    cap = Capture()
    exporter = OtlpExporter("http://x/api/public/otel/v1/traces", "pk", "sk", post=cap, batch_size=100,
                            flush_interval=60)
    for i in range(5):
        exporter.submit({"name": f"s{i}", "traceId": "0" * 32, "spanId": f"{i:016x}", "startTimeUnixNano": "1",
                         "endTimeUnixNano": "2", "attributes": []})
    t0 = time.monotonic()
    exporter.close(timeout=2)
    assert time.monotonic() - t0 < 2.5 and len(cap.spans()) == 5
    assert not [t for t in threading.enumerate() if t.name == "argus-otlp-exporter" and t.is_alive()]


def test_only_a_process_with_the_keys_and_the_switch_traces(tmp_path, monkeypatch):
    """The worker gets the Langfuse keys; the API and the scheduler do not, so they never trace even when enabled."""
    from argus.infrastructure.wiring import Settings, tracing_sink
    from argus.observability.tracing import TracingEventSink
    store = object()
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    s = Settings(secrets_dir=secrets)
    s.tracing_enabled = True
    assert tracing_sink(s, store) is store                       # enabled, but no keys: the API / scheduler case
    (secrets / "langfuse_public_key").write_text("pk-lf-x", encoding="utf-8")
    (secrets / "langfuse_secret_key").write_text("-".join(["sk", "lf", "x"]), encoding="utf-8")
    sink = tracing_sink(s, store)
    assert isinstance(sink, TracingEventSink) and sink.inner is store
    sink.exporter.close(timeout=0.1)
    s.tracing_enabled = False
    assert tracing_sink(s, store) is store                       # keys, but switched off


# --- B: model spans -------------------------------------------------------------------------------------------------
def test_model_call_becomes_a_filtered_child_span():
    from argus.observability.tracing import OtlpExporter, TracingEventSink
    from argus.observability.tracing import TracingLLM
    from argus.ports.ports import ModelReply, Usage

    class FakeLLM:
        model = "m-1"

        def decide(self, messages, tools):
            return ModelReply(text="SECRET REPLY", tool_calls=[], finish_reason="stop",
                              usage=Usage(input_tokens=11, output_tokens=7))

    posted = []
    ex = OtlpExporter("http://x", "pk", "sk", post=lambda u, h, b, t: posted.append(b), flush_interval=0.05)
    sink = TracingEventSink(None, ex)
    llm = TracingLLM(FakeLLM(), sink)
    sink.append_run_event("inc-1", "investigate", "enter", {})
    llm.decide([], [])
    sink.append_run_event("inc-1", "investigate", "exit", {})
    sink.append_run_event("inc-1", "record", "exit", {})
    ex.close()
    body = "".join(posted)
    assert "llm.decide" in body and "argus.input_tokens" in body and "m-1" in body
    assert '"generation"' in body and "langfuse.observation.usage_details" in body
    assert "SECRET REPLY" not in body


def test_model_error_propagates_and_is_traced_as_error():
    from argus.observability.tracing import OtlpExporter, TracingEventSink
    from argus.observability.tracing import TracingLLM

    class Boom:
        def decide(self, messages, tools):
            raise RuntimeError("down")

    ex = OtlpExporter("http://x", "pk", "sk", post=lambda *a: None)
    sink = TracingEventSink(None, ex)
    with __import__("pytest").raises(RuntimeError):
        TracingLLM(Boom(), sink).decide([], [])
    ex.close()


# --- C: the existing UI links to the trace ---------------------------------------------------------------------------
def test_incident_view_links_to_langfuse_for_operators_only(make_app):
    from fastapi.testclient import TestClient
    from pwdlib import PasswordHash
    from argus.adapters.inbound.http import build_api
    app = make_app()
    h = PasswordHash.recommended().hash("a-long-password")
    app.store.upsert_principal("alice", "human", "operator", ["lab"], h)
    app.store.upsert_principal("vera", "human", "viewer", ["lab"], h)
    inc = incident(app, WORKER)
    api = TestClient(build_api(app))

    def get(user, path):
        tok = api.post("/api/v1/auth/token", data={"username": user, "password": "a-long-password"}).json()["access_token"]
        return api.get(path, headers={"Authorization": f"Bearer {tok}"}).json()

    assert "trace_url" not in get("alice", f"/api/v1/incidents/{inc.id}")             # unset: no link
    app.settings.langfuse_ui_url, app.settings.langfuse_project_id = "http://127.0.0.1:3000", "p1"
    url = get("alice", f"/api/v1/incidents/{inc.id}")["trace_url"]
    assert url == f"http://127.0.0.1:3000/project/p1/traces?search={inc.id}"
    assert "view_traces" in get("alice", "/api/v1/me")["actions"]
    assert "trace_url" not in get("vera", f"/api/v1/incidents/{inc.id}")
    assert "view_traces" not in get("vera", "/api/v1/me")["actions"]


def test_stored_run_events_carry_the_trace_id(make_app):
    cap = Capture()
    app, exporter = traced_app(make_app, cap)
    inc = app.runner.run(incident(app, WORKER).id)
    exporter.close(timeout=5)
    ids = {e["data"].get("trace_id") for e in app.store.list_run_events(inc.id, 0)}
    assert ids == {s["traceId"] for s in cap.spans()}
