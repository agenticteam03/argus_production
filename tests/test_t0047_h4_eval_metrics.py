"""T-0047 H4 step 1 (ACR-0024 §3.8): the evaluation measures the hypotheses. A case's label may name
`expected_hypotheses` (supported / ruled_out: targets or cause classes); a replay keeps the final decision's ranked
list; the summary gives top-1 / top-3 root-cause accuracy over the ranking, ruled-out recall, the
`ranking_disagrees` rate and the H1 problem rate; and `unsupported_root_cause` is a hard check (0)."""
from __future__ import annotations

import re

import pytest
import yaml

from argus.adapters.outbound.llm import ScriptedLLM
from argus.tooling.model_harness import STATE_TOOL
from test_core import ROOT

CASES = ROOT / "tests" / "eval" / "cases"
API, CACHE = "vm-166/container:argus-lab-api", "vm-166/container:argus-lab-cache"


@pytest.fixture()
def ev(monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation
    return evaluation


def _case(ev, **label):
    return ev.Case.model_validate({"id": "x", "category": "class", "target": API, "request": "report",
                                   "reason": "api returns errors",
                                   "label": {"outcome": "diagnosed", "root_cause": CACHE, **label}})


def _run(ev, hypotheses=(), **kw):
    base = dict(case_id="x", outcome="diagnosed", incident_class="dependency_unavailable", root_cause_target=CACHE,
                diagnosis="the cache is stopped", findings=[], model_calls=2, reads=[], passages=[],
                audit_events=[], hypotheses=list(hypotheses), observed=[API, CACHE])
    base.update(kw)
    return ev.CaseRun(**base)


def h(hid, target, rank, status="supported", chosen=False, cause_class="dependency_unavailable"):
    return {"id": hid, "target": target, "cause_class": cause_class, "status": status, "rank": rank,
            "chosen": chosen}


# --- the labels --------------------------------------------------------------------------------------------------------
def test_the_labeled_cases_name_the_cause_and_the_victim(ev):
    labeled = [c for c in ev.load_cases(CASES) if c.label.expected_hypotheses]
    assert len(labeled) == 18
    for c in labeled:
        assert (c.label.root_cause in c.label.expected_hypotheses.supported
                and set(c.label.expected_hypotheses.supported) <= {c.label.root_cause, "memory_exhaustion"}
                if c.id == "dep-cache-oom-killed"
                else c.label.expected_hypotheses.supported == [c.label.root_cause])
        assert c.label.expected_hypotheses.ruled_out == [c.target] != [c.label.root_cause]


def test_an_unknown_key_in_expected_hypotheses_is_refused(ev, tmp_path):
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump({
        "id": "bad", "category": "class", "target": API, "request": "report", "reason": "x",
        "label": {"outcome": "diagnosed", "expected_hypotheses": {"supported": [CACHE], "maybe": [API]}}}),
        encoding="utf-8")
    with pytest.raises(ValueError, match="bad"):
        ev.load_cases(tmp_path)


def test_the_expected_cause_defaults_to_the_root_cause(ev):
    assert _case(ev).label.expected_causes() == [CACHE]
    assert _case(ev, expected_hypotheses={"supported": ["dependency_unavailable"]}).label.expected_causes() == [
        "dependency_unavailable"]
    assert _case(ev, root_cause=None).label.expected_causes() == []


# --- the metrics -------------------------------------------------------------------------------------------------------
def test_top_k_by_target_or_cause_class(ev):
    c = _case(ev)
    first = _run(ev, [h("h1", CACHE, 1, chosen=True), h("h2", API, 2, status="ruled_out")])
    second = _run(ev, [h("h1", API, 1), h("h2", "vm-166/host:vm-166", 2), h("h3", CACHE, 3, chosen=True)])
    assert (ev.top_k(c, first, 1), ev.top_k(c, second, 1), ev.top_k(c, second, 3)) == (True, False, True)
    by_class = _case(ev, expected_hypotheses={"supported": ["dependency_unavailable"]})
    assert ev.top_k(by_class, _run(ev, [h("h1", None, 1)]), 1) is True
    assert ev.top_k(c, _run(ev), 1) is None                     # no hypotheses stated: not counted


def test_ruled_out_recall_counts_only_what_was_ruled_out(ev):
    c = _case(ev, expected_hypotheses={"ruled_out": [API, "vm-166/host:vm-166"]})
    assert ev.ruled_out_found(c, _run(ev, [h("h1", CACHE, 1), h("h2", API, 2, status="ruled_out")])) == (1, 2)
    assert ev.ruled_out_found(c, _run(ev, [h("h1", CACHE, 1), h("h2", API, 2, status="untested")])) == (0, 2)
    assert ev.ruled_out_found(_case(ev), _run(ev, [h("h1", CACHE, 1)])) is None


def test_the_summary_reports_the_ranking_metrics(ev):
    c = _case(ev, expected_hypotheses={"supported": [CACHE], "ruled_out": [API]})
    good = _run(ev, [h("h1", CACHE, 1, chosen=True), h("h2", API, 2, status="ruled_out")])
    wrong = _run(ev, [h("h1", API, 1), h("h2", CACHE, 2, chosen=True)], ranking_disagrees=True,
                 hypothesis_problems=["h1: supported without an observation of its own target"])
    silent = _run(ev)                                             # a model run that stated none
    baseline = _run(ev, model_calls=0)                            # no model: not in any denominator
    s = ev.summarize([(c, good), (c, wrong), (c, silent), (c, baseline)])["hypotheses"]
    assert s == {"hypotheses_stated": 2 / 3, "top1_root_cause": 0.5, "top3_root_cause": 1.0,
                 "ruled_out_recall": 0.5, "ranking_disagrees": 0.5, "hypothesis_problem_rate": 1 / 3}
    assert set(ev.summarize([(c, baseline)])["hypotheses"].values()) == {None}


def test_unsupported_root_cause_is_a_hard_check(ev):
    assert ev.unsupported_root_cause(_run(ev, observed=[API])) == 1
    assert ev.unsupported_root_cause(_run(ev, observed=[API, CACHE])) == 0
    assert ev.unsupported_root_cause(_run(ev, observed=[], outcome="no_action_escalated")) == 0
    assert ev.unsupported_root_cause(_run(ev, observed=None)) == 0         # not recorded (an older result)
    s = ev.summarize([(_case(ev), _run(ev, observed=[API]))])
    assert s["hard"]["unsupported_root_cause"] == 1


# --- a replay keeps the final list -------------------------------------------------------------------------------------
def _ids(ctx: str, target: str) -> list[str]:
    """The ids of the container.status evidence of `target` in the model's context."""
    blocks = re.findall(r'<evidence id="([^"]+)"([^>]*)>\n?([^\n]*)', ctx)
    return [i for i, attrs, text in blocks if text.startswith(f"{target}: state=")]


def _script(ctx: str):
    if not _ids(ctx, CACHE):
        return {"calls": [("get_container_status", {"target": API}), ("get_container_status", {"target": CACHE}),
                          (STATE_TOOL, {"hypotheses": [
                              {"id": "h1", "statement": "the cache is down", "cause_class": "dependency_unavailable",
                               "target": CACHE, "relation": "dependency", "status": "untested"},
                              {"id": "h2", "statement": "the api itself fails", "cause_class": "other",
                               "target": API, "relation": "self", "status": "untested"}]})]}
    cache, api = _ids(ctx, CACHE)[-1], _ids(ctx, API)[-1]
    return {"calls": [("conclude", {"diagnosis": "the cache is stopped, so the api fails", "evidence_ids": [cache],
                                    "confidence": "high", "root_cause_target": CACHE, "chosen": "h1",
                                    "hypotheses": [
                                        {"id": "h1", "statement": "the cache is down",
                                         "cause_class": "dependency_unavailable", "target": CACHE,
                                         "relation": "dependency", "status": "supported", "support": [cache]},
                                        {"id": "h2", "statement": "the api itself fails", "cause_class": "other",
                                         "target": API, "relation": "self", "status": "ruled_out",
                                         "against": [api]}]})]}


def test_a_replay_keeps_the_final_ranked_list(ev, tmp_path):
    c = next(x for x in ev.load_cases(CASES) if x.id == "dep-cache-stopped")
    run = ev.run_case(c, workdir=tmp_path, llm=ScriptedLLM(_script), strategy="model_loop")   # its class: baseline
    assert run.outcome == "diagnosed" and run.root_cause_target == CACHE, run.invalid_decisions
    assert [(x["id"], x["status"], x["rank"], x["chosen"]) for x in run.hypotheses] == [
        ("h1", "supported", 1, True), ("h2", "ruled_out", 2, False)]
    assert run.ranking_disagrees is False and run.hypothesis_problems == []
    assert CACHE in run.observed and ev.unsupported_root_cause(run) == 0
    assert (ev.top_k(c, run, 1), ev.ruled_out_found(c, run)) == (True, (1, 1))


def test_a_target_named_by_an_observation_on_its_host_counts_as_observed():
    """pg-leaker: the database's sessions name the leaking client; the baseline's diagnosis is not unsupported."""
    from types import SimpleNamespace

    from argus.domain.model import TargetRef
    from argus.evaluation.replay import _observed
    db = "vm-166/container:argus-lab-db"
    refs = [TargetRef.parse(t) for t in (db, "vm-166/container:argus-lab-leaker", "vm-095/container:argus-lab-leaker",
                                         "vm-166/container:argus-lab-leak")]
    health = SimpleNamespace(target=db, status="ok", kind="observation", capability="database.health",
                             values={"top_clients": ["argus-lab-leaker"]})
    failed = SimpleNamespace(target=db, status="timeout", kind="observation", capability="database.health",
                             values={"x": "argus-lab-leak"})
    assert _observed([health, failed], refs) == [db, "vm-166/container:argus-lab-leaker"]


def test_a_listing_that_names_every_container_does_not_count_as_observing_them():
    """`container.list` names every container of its host: the root cause it lists is still unobserved, so a diagnosis
    of it with no read of it stays `unsupported_root_cause` (ACR-0024 §3.8, never relaxed)."""
    from types import SimpleNamespace

    from argus.domain.model import TargetRef
    from argus.evaluation.replay import _observed
    from argus.evaluation.score import unsupported_root_cause
    api, cache = "vm-166/container:argus-lab-api", "vm-166/container:argus-lab-cache"
    refs = [TargetRef.parse(t) for t in (api, cache)]
    listing = SimpleNamespace(target="vm-166/host", status="ok", kind="observation", capability="container.list",
                              values={"containers": [{"name": "argus-lab-api"}, {"name": "argus-lab-cache"}]})
    status = SimpleNamespace(target=api, status="ok", kind="observation", capability="container.status", values={})
    observed = _observed([listing, status], refs)
    assert observed == [api, "vm-166/host"]
    run = SimpleNamespace(observed=observed, outcome="diagnosed", root_cause_target=cache)
    assert unsupported_root_cause(run) == 1
