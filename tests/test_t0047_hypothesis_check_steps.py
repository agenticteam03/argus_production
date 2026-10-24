"""T-0047 (ACR-0024 §3.2, as built): which step each hypothesis check applies to.

A read step's `state_hypotheses` list is checked before that step's reads run, so a cause marked `supported` while its
own read is requested in the same step looked unsupported (#274's batch: `dep-cache-paused` trial 3,
`dep-cache-restarting` trial 2, both clean at their `conclude`). The evidence checks (own-target support, `ruled_out`
without `against`, an external cause's support) apply on `conclude` / `escalate` only; a read step keeps the structural
ones. Each problem in a replay row names the step and the decision it came from.
"""
from __future__ import annotations

import json
import re

import pytest

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import Conclude, Escalate, EvidenceRef, TargetRef, UseReadTools
from argus.orchestration.view import InvestigationView
from argus.ports.ports import ModelReply, ModelToolCall
from argus.tooling.model_harness import STATE_TOOL, ModelHarness
from test_core import ROOT

WORKER = "vm-166/container:argus-lab-worker"
DB = "vm-166/container:argus-lab-db"
HOST = "vm-166/host:vm-166"
API, CACHE = "vm-166/container:argus-lab-api", "vm-166/container:argus-lab-cache"
CASES = ROOT / "tests" / "eval" / "cases"


def _view() -> InvestigationView:
    from argus.capabilities.catalog import build_catalog
    evidence = [EvidenceRef(evidence_id="ev2", sha256="0" * 64, capability="container.status", status="ok",
                            model_text="the db's status", target=DB, kind="observation")]
    return InvestigationView(incident=None, incident_class=None, findings=[], passages=[], evidence=evidence,
                             decisions_so_far=[], offered_specs=[s for s in build_catalog() if s.name == "container.status"],
                             scope=[TargetRef.parse(t) for t in (WORKER, DB, HOST)], steps_left=5,
                             max_reads_per_step=2)


def _h(i: int = 1, target: str | None = WORKER, relation: str = "self", status: str = "supported",
       support=("ev2",), against=()) -> dict:
    return {"id": f"h{i}", "statement": f"hypothesis {i}", "cause_class": "other", "target": target,
            "relation": relation, "status": status, "support": list(support), "against": list(against)}


def _decide(*calls):
    reply = ModelReply(text=None, tool_calls=[ModelToolCall(name=n, arguments_json=json.dumps(a)) for n, a in calls],
                       finish_reason="tool_calls")
    return ModelHarness(llm=None).convert(reply, _view())


def _read_step(hypotheses):
    return _decide(("get_container_status", {"target": WORKER}), (STATE_TOOL, {"hypotheses": hypotheses}))


def _conclude(hypotheses):
    return _decide(("conclude", {"diagnosis": "the worker was OOM-killed by its limit", "evidence_ids": ["ev2"],
                                 "confidence": "high", "root_cause_target": WORKER, "chosen": "h1",
                                 "hypotheses": hypotheses}))


# --- the harness -----------------------------------------------------------------------------------------------------
def test_supported_while_its_own_read_is_requested_is_not_a_problem_on_the_read_step():
    d = _read_step([_h(1)])                                # the worker's status is read in this same step
    assert isinstance(d, UseReadTools) and d.hypothesis_problems == []


def test_the_same_list_on_conclude_without_the_read_is_still_a_problem():
    d = _conclude([_h(1)])                                 # only the db's status was ever read
    assert isinstance(d, Conclude)
    assert d.hypothesis_problems == ["h1: supported without an observation or metric snapshot of its own target"]


def test_the_other_evidence_checks_wait_for_the_decision_too():
    hyps = [_h(1), _h(2, DB, "dependency", "ruled_out", support=()), _h(3, None, "external", support=())]
    assert _read_step(hyps).hypothesis_problems == []
    escalated = _decide(("escalate", {"reason": "nothing conclusive", "hypotheses": hyps}))
    assert isinstance(escalated, Escalate)
    assert escalated.hypothesis_problems == [
        "h1: supported without an observation or metric snapshot of its own target",
        "h2: ruled out without evidence against it",
        "h3: an external cause supported without an observation of a target in scope"]


@pytest.mark.parametrize("hypotheses, problem", [
    ([_h(1, support=("ev9",))], "h1: cites evidence not stored for this incident: ['ev9']"),
    ([_h(1, DB, "dependency", support=("ev2",), against=("ev2",))], "h1: the same evidence both for and against it"),
    ([_h(1, None, "dependency", "untested", support=())], "h1: no target, but its relation is dependency, not external"),
    ([_h(1, "vm-095/container:argus-lab-db", "dependency", "untested", support=())],
     "h1: target vm-095/container:argus-lab-db is not in the incident's scope"),
    ([_h(1), _h(1, DB, "dependency", "untested", support=())], "h1: the same id twice"),
    ([_h(i, DB, "dependency", "untested", support=()) for i in range(1, 7)], "6 hypotheses: at most 5"),
    ([{"id": "h9", "statement": "x"}], "a hypothesis fails its schema"),
])
def test_a_read_step_keeps_the_structural_checks(hypotheses, problem):
    d = _read_step(hypotheses)
    assert isinstance(d, UseReadTools) and any(p.startswith(problem) for p in d.hypothesis_problems), d.hypothesis_problems


# --- a replay: the #274 shape -------------------------------------------------------------------------------------------
def _ids(ctx: str, target: str) -> list[str]:
    blocks = re.findall(r'<evidence id="([^"]+)"([^>]*)>\n?([^\n]*)', ctx)
    return [i for i, _, text in blocks if text.startswith(f"{target}: state=")]


def _script(read_the_cache: bool):
    """Step 1 reads (the cache's status too, or the api's only) and states the cache `supported`; step 2 concludes."""
    def script(ctx: str):
        if not _ids(ctx, API):
            reads = [("get_container_status", {"target": API})]
            if read_the_cache:
                reads.append(("get_container_status", {"target": CACHE}))
            return {"calls": [*reads, (STATE_TOOL, {"hypotheses": [
                {"id": "h1", "statement": "the cache is down", "cause_class": "dependency_unavailable",
                 "target": CACHE, "relation": "dependency", "status": "supported"}]})]}
        api = _ids(ctx, API)[-1]
        support = _ids(ctx, CACHE)[-1:] or [api]
        return {"calls": [("conclude", {"diagnosis": "the cache is paused, so the api fails", "evidence_ids": support,
                                        "confidence": "high", "root_cause_target": CACHE, "chosen": "h1",
                                        "hypotheses": [
                                            {"id": "h1", "statement": "the cache is down",
                                             "cause_class": "dependency_unavailable", "target": CACHE,
                                             "relation": "dependency", "status": "supported", "support": support},
                                            {"id": "h2", "statement": "the api itself fails", "cause_class": "other",
                                             "target": API, "relation": "self", "status": "ruled_out",
                                             "against": [api]}]})]}
    return script


@pytest.fixture()
def ev(monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation
    return evaluation


def test_a_replay_of_the_274_shape_has_no_problem(ev, tmp_path):
    c = next(x for x in ev.load_cases(CASES) if x.id == "dep-cache-paused")
    run = ev.run_case(c, workdir=tmp_path, llm=ScriptedLLM(_script(read_the_cache=True)), strategy="model_loop")
    assert run.outcome == "diagnosed" and run.root_cause_target == CACHE, run.invalid_decisions
    assert run.hypothesis_problems == [] and ev.unsupported_root_cause(run) == 0


def test_a_replay_that_never_reads_the_cause_names_the_step_and_decision_of_its_problem(ev, tmp_path):
    c = next(x for x in ev.load_cases(CASES) if x.id == "dep-cache-paused")
    run = ev.run_case(c, workdir=tmp_path, llm=ScriptedLLM(_script(read_the_cache=False)), strategy="model_loop")
    assert run.outcome == "diagnosed" and run.root_cause_target == CACHE, run.invalid_decisions
    assert run.hypothesis_problems == [
        "step 2 conclude: h1: supported without an observation or metric snapshot of its own target"]
