"""knowledge.runbook (query_runbook): the in-worker capability of ARCHITECTURE §10.5/§12 that lets a strategy read
any runbook of the library during an investigation — how a branch runbook is reached when the evidence points to
its cause (§3). It goes through InvokeCapability like every read: policy, audit, evidence; it never calls a VM.
"""
from __future__ import annotations

from argus.adapters.outbound.llm import ScriptedLLM
from argus.application.invoke_capability import InvocationContext
from argus.domain.model import IncidentOutcome

from test_core import FakeMetrics, FakeTargetAgent, incident, make_app  # noqa: F401  (make_app is a fixture)

CLIENT = "vm-166/container:argus-lab-client"


def _ctx(app, inc):
    return InvocationContext(incident=inc, caller="test", scope=app.runner.scope(inc.target))


def test_query_runbook_reads_the_library_in_worker(make_app):
    app = make_app()
    inc = incident(app, CLIENT)
    obs, ref = app.runner.invoke(_ctx(app, inc), "query_runbook",
                                 {"target": CLIENT, "runbook_id": "RB-009", "query": "dns resolution docker network"})
    assert obs.status == "ok" and obs.capability == "knowledge.runbook" and obs.executor == "argus_internal"
    passages = obs.values["passages"]
    assert 1 <= len(passages) <= 3
    assert all(p["runbook_id"] == "RB-009" and p["version"] and p["status"] and len(p["sha256_prefix"]) == 16 for p in passages)
    assert "[REDACTED" not in str(passages)                 # a full hash would look like a secret to the redactor
    assert "RB-009" in obs.model_text and "DNS" in obs.model_text
    assert ref is not None and app.store.get_evidence([ref.evidence_id])[0].capability == "knowledge.runbook"
    assert FakeTargetAgent.calls == []                       # in-worker: no VM is called


def test_query_runbook_without_matching_words_still_returns_the_workflow(make_app):
    app = make_app()
    inc = incident(app, CLIENT)
    obs, _ = app.runner.invoke(_ctx(app, inc), "query_runbook", {"target": CLIENT, "runbook_id": "RB-009", "query": "zzzz"})
    assert obs.status == "ok" and obs.values["passages"]


def test_query_runbook_refuses_unknown_or_malformed_ids(make_app):
    app = make_app()
    inc = incident(app, CLIENT)
    unknown, _ = app.runner.invoke(_ctx(app, inc), "query_runbook", {"target": CLIENT, "runbook_id": "RB-999", "query": "x"})
    assert unknown.status == "error" and unknown.error_category == "not_found"
    bad, _ = app.runner.invoke(_ctx(app, inc), "query_runbook", {"target": CLIENT, "runbook_id": "../secrets", "query": "x"})
    assert bad.status == "refused" and bad.error_category == "invalid_args"


def test_query_runbook_is_limited_by_policy(make_app):
    app = make_app()
    inc = incident(app, CLIENT)
    ctx = _ctx(app, inc)
    args = {"target": CLIENT, "runbook_id": "RB-003", "query": "dependency"}
    results = [app.runner.invoke(ctx, "query_runbook", dict(args))[0] for _ in range(4)]
    assert [r.status for r in results[:3]] == ["ok"] * 3
    assert results[3].status == "refused"                    # max_per_incident: 3 (config/policy.yaml)


def test_branch_runbooks_are_offered_and_read_in_a_diagnosis(make_app):
    seen = {}

    def script(ctx: str):
        if "section(s) for" not in ctx:                   # query_runbook not answered yet (detect already stored evidence)
            seen.setdefault("first", ctx)
            return {"calls": [("query_runbook", {"target": CLIENT, "runbook_id": "RB-009",
                                                 "query": "name does not resolve between docker networks"})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "backend on another network (RB-009)", "evidence_ids": ids[-1:],
                                        "confidence": "medium", "root_cause_target": "vm-166/container:argus-lab-backend"})]}
    app = make_app(llm=ScriptedLLM(script), metrics=FakeMetrics({CLIENT: {"dependency_probe_min": 0}}))
    inc = app.runner.run(incident(app, CLIENT, reason="the client cannot reach its backend").id)
    assert inc.incident_class == "dependency_unavailable" and inc.outcome == IncidentOutcome.diagnosed
    first = seen["first"]
    assert "branch runbooks" in first and "RB-009 DNS/network connectivity failure" in first and "query_runbook" in first
    caps = [e.capability for e in app.store.list_evidence(inc.id)]
    assert "knowledge.runbook" in caps
