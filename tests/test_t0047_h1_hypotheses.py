"""T-0047 H1 (ACR-0024 §3.1-§3.2): model strategies state hypotheses, and the harness checks them log-only.

The decision tools carry `hypotheses` (and `chosen` on `conclude`). The harness keeps every decision it kept before,
drops a hypothesis that fails its schema, and attaches each would-be refusal of §3.2 as `hypothesis_problems`; the
runner audits them as `hypothesis.invalid`. Nothing is refused until the evaluation (H4).
"""
from __future__ import annotations

import json

import pytest

from argus.domain.model import Conclude, Escalate, EvidenceRef, TargetRef
from argus.orchestration.view import InvestigationView
from argus.ports.ports import ModelReply, ModelToolCall
from argus.tooling.model_harness import ModelHarness
from test_core import FakeMetrics, incident, make_app  # noqa: F401  (make_app is a fixture)

WORKER = "vm-166/container:argus-lab-worker"
DB = "vm-166/container:argus-lab-db"
HOST = "vm-166/host:vm-166"


def _ev(n: int, target: str | None, kind: str = "observation") -> EvidenceRef:
    return EvidenceRef(evidence_id=f"ev{n}", sha256="0" * 64, capability="container.status", status="ok",
                       model_text=f"evidence {n}", target=target, kind=kind)


EVIDENCE = [_ev(1, WORKER), _ev(2, DB), _ev(3, WORKER, "alert"), _ev(4, HOST, "metric_snapshot")]


def _view(evidence=EVIDENCE) -> InvestigationView:
    return InvestigationView(incident=None, incident_class=None, findings=[], passages=[], evidence=list(evidence),
                             decisions_so_far=[], offered_specs=[], scope=[TargetRef.parse(t) for t in (WORKER, DB, HOST)],
                             steps_left=5, max_reads_per_step=2)


def _h(i: int = 1, target: str | None = WORKER, relation: str = "self", status: str = "supported",
       support=("ev1",), against=(), cause_class: str = "oom") -> dict:
    return {"id": f"h{i}", "statement": f"hypothesis {i}", "cause_class": cause_class, "target": target,
            "relation": relation, "status": status, "support": list(support), "against": list(against)}


def _conclude(hypotheses=None, chosen: str | None = "h1", rct: str | None = WORKER, **extra):
    args = {"diagnosis": "the worker was OOM-killed by its 64 MiB limit", "evidence_ids": ["ev1"],
            "confidence": "high", "root_cause_target": rct, **extra}
    if hypotheses is not None:
        args["hypotheses"] = hypotheses
    if chosen is not None:
        args["chosen"] = chosen
    return _decide("conclude", args)


def _decide(name: str, args: dict, view=None):
    reply = ModelReply(text=None, tool_calls=[ModelToolCall(name=name, arguments_json=json.dumps(args))],
                       finish_reason="tool_calls")
    return ModelHarness(llm=None).convert(reply, view or _view())


def _problems(d) -> str:
    return " | ".join(d.hypothesis_problems)


# --- the schemas -------------------------------------------------------------------------------------------------------
def test_the_decision_tools_carry_hypotheses_and_conclude_carries_chosen():
    tools = {t.name: t.parameters_schema for t in ModelHarness(llm=None).tool_definitions(_view())}
    hyp = tools["conclude"]["properties"]["hypotheses"]
    assert hyp["maxItems"] == 5 and hyp["items"]["properties"]["id"]["enum"] == ["h1", "h2", "h3", "h4", "h5"]
    assert hyp["items"]["properties"]["target"]["enum"] == [WORKER, DB, HOST, None]
    assert hyp["items"]["properties"]["relation"]["enum"] == ["self", "dependency", "host", "external"]
    assert "chosen" in tools["conclude"]["properties"] and "hypotheses" not in tools["conclude"]["required"]
    assert tools["escalate"]["properties"]["hypotheses"] == hyp


def test_the_system_prompt_asks_for_hypotheses():
    from argus.tooling.model_harness import SYSTEM_PROMPT
    assert "Hypotheses" in SYSTEM_PROMPT and "never chosen" in SYSTEM_PROMPT


# --- a sound list: kept, no problems -------------------------------------------------------------------------------
def test_a_sound_conclusion_has_no_problems():
    d = _conclude([_h(1), _h(2, DB, "dependency", "ruled_out", support=(), against=("ev2",)),
                   _h(3, None, "external", "untested", support=())])
    assert isinstance(d, Conclude) and d.chosen == "h1" and len(d.hypotheses) == 3 and d.hypothesis_problems == []


def test_a_host_hypothesis_is_supported_by_a_metric_snapshot_of_the_host():
    d = _conclude([_h(1, HOST, "host", support=("ev4",))], rct=HOST)
    assert d.hypothesis_problems == []


def test_old_replies_without_hypotheses_still_convert():
    d = _conclude(None, chosen=None)
    assert isinstance(d, Conclude) and d.hypotheses == [] and d.root_cause_target == WORKER
    assert d.hypothesis_problems == ["a conclusion without hypotheses"]
    e = _decide("escalate", {"reason": "nothing conclusive", "evidence_ids": ["ev1"]})
    assert isinstance(e, Escalate) and e.hypotheses == [] and e.hypothesis_problems == []


# --- each §3.2 check: the decision stands, the problem is recorded ----------------------------------------------------
def test_unknown_evidence_and_the_same_evidence_for_and_against():
    d = _conclude([_h(1, support=("ev1", "ev9")), _h(2, DB, "dependency", "ruled_out", support=("ev2",),
                                                       against=("ev2",))])
    assert isinstance(d, Conclude)
    assert "h1: cites evidence not stored" in _problems(d) and "h2: the same evidence both for and against" in _problems(d)


def test_supported_needs_an_observation_of_its_own_target():
    other = _conclude([_h(1, support=("ev2",))])                     # the db's status, not the worker's
    alert = _conclude([_h(1, support=("ev3",))])                     # an alert is not an observation
    assert "h1: supported without an observation" in _problems(other)
    assert "h1: supported without an observation" in _problems(alert)


def test_ruled_out_needs_evidence_against():
    d = _conclude([_h(1), _h(2, DB, "dependency", "ruled_out", support=())])
    assert d.hypothesis_problems == ["h2: ruled out without evidence against it"]


def test_a_conclusion_must_tie_its_root_cause_to_a_supported_chosen_hypothesis():
    assert "without a chosen hypothesis" in _problems(_conclude([_h(1)], chosen=None))
    assert "is not one of the hypotheses" in _problems(_conclude([_h(1)], chosen="h4"))
    assert "is untested, not supported" in _problems(_conclude([_h(1, status="untested", support=())]))
    assert "not the root_cause_target" in _problems(_conclude([_h(1, DB, "dependency", support=("ev2",))]))


def test_targets_must_be_in_scope_and_only_external_has_none():
    out_of_scope = _conclude([_h(1), _h(2, "vm-095/container:argus-lab-db", "dependency", "untested", support=())])
    no_target = _conclude([_h(1), _h(2, None, "dependency", "untested", support=())])
    assert "h2: target vm-095/container:argus-lab-db is not in the incident's scope" in _problems(out_of_scope)
    assert "h2: no target, but its relation is dependency" in _problems(no_target)


def test_an_external_cause_needs_an_in_scope_observation_and_is_never_chosen():
    unsupported = _decide("escalate", {"reason": "provider outage", "hypotheses": [
        _h(1, None, "external", support=("ev3",))]})
    supported = _decide("escalate", {"reason": "provider outage", "hypotheses": [
        _h(1, None, "external", support=("ev1",))]})
    assert isinstance(unsupported, Escalate) and "external cause supported without an observation" in _problems(unsupported)
    assert supported.hypothesis_problems == [] and supported.hypotheses[0].relation == "external"
    chosen = _conclude([_h(1, None, "external", support=("ev1",))], rct=None)
    assert "chosen h1 is external" in _problems(chosen)


def test_too_many_hypotheses_or_a_malformed_one_are_dropped_not_refused():
    many = _conclude([_h(1)] + [_h(i, DB, "dependency", "untested", support=()) for i in range(2, 7)])
    assert isinstance(many, Conclude) and len(many.hypotheses) == 5 and "6 hypotheses: at most 5" in _problems(many)
    bad = _conclude([_h(1), {"id": "h9", "statement": "x"}, _h(1, DB, "dependency", "untested", support=())])
    assert [h.id for h in bad.hypotheses] == ["h1"]
    assert "fails its schema" in _problems(bad) and "h1: the same id twice" in _problems(bad)
    assert "hypotheses must be a list" in _problems(_conclude({"h1": "x"}, chosen=None, rct=None))


# --- the runner audits the problems, and the run ends as before ---------------------------------------------------------
@pytest.mark.parametrize("runner", ["plain", "langgraph"])
def test_the_runner_audits_hypothesis_problems_and_keeps_the_decision(make_app, monkeypatch, runner):
    monkeypatch.setenv("ARGUS_RUNNER", runner)
    def script(ctx):
        if "container.status" not in ctx:
            return {"calls": [("get_container_status", {"target": WORKER})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "OOM-killed by its 64 MiB limit", "evidence_ids": ids[-1:],
                                        "confidence": "high", "root_cause_target": WORKER,
                                        "hypotheses": [_h(1, support=ids[-1:]), _h(2, WORKER, "self", "ruled_out",
                                                                                     support=())],
                                        "chosen": "h1"})]}
    from argus.adapters.outbound.llm import ScriptedLLM
    from argus.domain.model import IncidentOutcome
    app = make_app(llm=ScriptedLLM(script),
                   metrics=FakeMetrics({WORKER: {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}}))
    inc = app.runner.run(incident(app, WORKER).id)
    assert type(app.runner).__name__ == {"plain": "SkeletonRunner", "langgraph": "GraphRunner"}[runner]
    assert inc.outcome == IncidentOutcome.diagnosed and inc.root_cause_target == WORKER
    audit = app.store.list_for(inc.id)
    invalid = [a for a in audit if a.event == "hypothesis.invalid"]
    assert len(invalid) == 1 and invalid[0].category == "decision" and invalid[0].actor == "model"
    assert invalid[0].detail["decision"] == "conclude"
    assert invalid[0].detail["problems"] == ["h2: ruled out without evidence against it"]
    concluded = next(a for a in audit if a.event == "decision.conclude")
    assert concluded.detail["chosen"] == "h1" and concluded.detail["hypotheses"][0]["id"] == "h1"
    ev = app.store.list_evidence(inc.id)[-1]
    assert ev.target == WORKER and ev.kind == "observation"      # the reference the checks read carries both
