"""T-0031, phase 8: the standing write-gate test (ARCHITECTURE §22.2, §13.3, §13.4).

While only cache start is released, a model reply proposing `container.restart` must end as `no_action_escalated`,
with no approval, no write node and no request to any action endpoint. It runs in every build (CI), on both runners.
The deployment half is `ops/write-gate-check.sh` (tests/test_write_gate_check.py).
"""
from __future__ import annotations

import pytest
import yaml

from argus.adapters.outbound.llm import ScriptedLLM
from argus.capabilities.catalog import build_catalog
from argus.domain.model import IncidentOutcome, IncidentStatus
from argus.policy.engine import PolicyEngine
from test_core import ROOT, FakeMetrics, FakeTargetAgent, incident, make_app  # noqa: F401  (make_app = fixture)

WORKER_166 = "vm-166/container:argus-lab-worker"
CACHE_PAIR = {"capability": "container.start", "target": "vm-166/container:argus-lab-cache"}
READ_ONLY = {"READ_ONLY_SAFE", "READ_ONLY_SENSITIVE"}
WRITE_NODES = {"propose_action", "request_approval", "await_approval", "precheck_action", "execute_write"}

# Every way a model reply can put a restart on the table: the capability name, a function-style name, a proposal
# tool, and a restart hidden behind a legitimate read in the same reply (§13.4: none of the calls is executed).
PROPOSALS = {
    "capability_name": [("container.restart", {"target": WORKER_166})],
    "function_name": [("restart_container", {"target": WORKER_166})],
    "proposal_tool": [("propose_remediation", {"capability": "container.restart", "target": WORKER_166,
                                               "reason": "OOM restart loop"})],
    "mixed_with_a_read": [("get_container_status", {"target": WORKER_166}),
                          ("restart_container", {"target": WORKER_166})],
}


@pytest.fixture()
def write_calls(monkeypatch):
    """Any non-GET request a target executor makes is recorded here; the read executors only have `get`."""
    seen: list[tuple[str, str, str]] = []
    for verb in ("post", "put", "patch", "delete"):
        monkeypatch.setattr(FakeTargetAgent, verb,
                            lambda self, path, *a, verb=verb, **k: seen.append((verb, self.url, path)), raising=False)
    return seen


@pytest.mark.parametrize("runner", ["plain", "langgraph"])
@pytest.mark.parametrize("proposal", list(PROPOSALS))
def test_a_proposed_restart_ends_escalated_with_no_approval_and_no_write(
        make_app,  # noqa: F811
        monkeypatch, write_calls, runner, proposal):
    monkeypatch.setenv("ARGUS_RUNNER", runner)
    metrics = FakeMetrics({WORKER_166: {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}})
    app = make_app(llm=ScriptedLLM(lambda ctx: {"calls": PROPOSALS[proposal]}), metrics=metrics)
    inc = app.runner.run(incident(app, WORKER_166).id)

    assert inc.outcome == IncidentOutcome.no_action_escalated and inc.status == IncidentStatus.escalated
    events = [a.event for a in app.store.list_for(inc.id)]
    assert "security.fabricated_tool" in events                                  # audited as a security event
    assert not [e for e in events if "approval" in e or e.startswith(("action.", "write."))]
    nodes = {e["node"] for e in app.store.list_run_events(inc.id)}
    assert not nodes & WRITE_NODES, nodes & WRITE_NODES
    assert write_calls == []                                                     # nothing reached an action endpoint
    assert not [p for _, p in FakeTargetAgent.calls if "restart" in p or "action" in p]
    if proposal == "mixed_with_a_read":                                          # the read in that reply never ran
        assert not [p for _, p in FakeTargetAgent.calls if p.endswith("/argus-lab-worker/status")]


def test_the_catalogue_registers_no_write_capability():
    specs = build_catalog()
    assert {s.safety_class for s in specs} <= READ_ONLY, {s.name: s.safety_class for s in specs
                                                          if s.safety_class not in READ_ONLY}
    names = {s.name for s in specs} | {s.model_name for s in specs}
    assert not names & {"container.restart", "restart_container", "propose_remediation"}


def test_the_policy_opens_only_cache_start_and_allows_only_reads():
    text = (ROOT / "config/policy.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["write_gate"]["open"] == [CACHE_PAIR]
    policy = PolicyEngine(data, text)
    assert policy.allowed_safety_classes <= READ_ONLY
    assert policy.write_gate_open == [CACHE_PAIR]
