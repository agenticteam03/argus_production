"""T-0049 R1 item 5: `knowledge.prior_incidents` (T-0039) made evaluable. A replay's store was empty, so the read
always answered "no prior closed incident". A case may now seed closed incidents (`prior_incidents:` in its YAML),
stored before the run: a precedent that helps (the same cause again) and one that misleads (the same target and class,
another cause), so a batch can see whether the model uses history or over-trusts it. No class offers the read yet;
these tests offer it through the class registry for the run only.
"""
from __future__ import annotations

import re

import pytest

from argus.adapters.outbound.llm import ScriptedLLM
from test_core import ROOT

CASES = ROOT / "tests" / "eval" / "cases"
READ = "query_prior_incidents"


@pytest.fixture()
def ev(monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation
    return evaluation


def _case(ev, case_id):
    return next(c for c in ev.load_cases(CASES) if c.id == case_id)


@pytest.fixture()
def offered(monkeypatch):
    """Offer the read to every class for this test only (the registry offers it to none)."""
    from argus.detectors.classes import CLASSES
    for c in CLASSES:
        monkeypatch.setattr(c, "tool_tags", set(c.tool_tags) | {"prior_incidents"})


def _ask_history_then_conclude(case):
    def script(ctx: str):
        if "prior closed incident" not in ctx:
            return {"calls": [(READ, {"target": case.target, "incident_class": case.label.incident_class, "k": 3})]}
        ids = re.findall(r'<evidence id="([^"]+)"', ctx)
        return {"calls": [("conclude", {"diagnosis": "a scripted conclusion after reading the history",
                                        "evidence_ids": ids[-1:], "confidence": "low",
                                        "root_cause_target": case.label.root_cause})]}
    return script


# --- the case format --------------------------------------------------------------------------------------------------
def test_a_case_may_seed_closed_incidents_and_unknown_keys_are_refused(ev):
    base = {"id": "x", "category": "class", "target": "vm-166/container:argus-lab-api", "request": "report",
            "reason": "r", "label": {"outcome": "diagnosed"}}
    prior = {"class": "dependency_unavailable", "target": "vm-166/container:argus-lab-api",
             "diagnosis": "the cache was paused", "root_cause": "vm-166/container:argus-lab-cache",
             "closed_at": "2026-10-01T10:00:00Z"}
    c = ev.Case.model_validate({**base, "prior_incidents": [prior]})
    p = c.prior_incidents[0]
    assert (p.incident_class, p.root_cause, p.outcome, p.confidence) == (
        "dependency_unavailable", "vm-166/container:argus-lab-cache", "diagnosed", "high")
    assert ev.Case.model_validate(base).prior_incidents == []
    with pytest.raises(ValueError):
        ev.Case.model_validate({**base, "prior_incidents": [{**prior, "maybe": 1}]})
    with pytest.raises(ValueError):
        ev.Case.model_validate({**base, "prior_incidents": [{**prior, "target": "argus-lab-api"}]})
    with pytest.raises(ValueError):
        ev.Case.model_validate({**base, "prior_incidents": [{**prior, "class": "no_such_class"}]})


def test_the_seeded_cases_hold_a_helpful_and_a_misleading_precedent(ev):
    seeded = {c.id: c for c in ev.load_cases(CASES) if c.prior_incidents}
    assert sorted(seeded) == ["dep-cache-paused", "restart-crash-01", "restart-oom-01"]
    for c in seeded.values():                                       # the same target and class as the case
        assert all((p.target, p.incident_class) == (c.target, c.label.incident_class) for p in c.prior_incidents)
    helpful = [p.diagnosis for cid in ("restart-oom-01", "dep-cache-paused") for p in seeded[cid].prior_incidents]
    assert all(("OOM" in d or "paused" in d) for d in helpful)
    misleading = seeded["restart-crash-01"].prior_incidents          # the case is a non-OOM crash
    assert len(misleading) == 1 and "OOM" in misleading[0].diagnosis and "non-OOM" not in misleading[0].diagnosis


# --- the replay -------------------------------------------------------------------------------------------------------
def test_a_seeded_case_answers_the_read_with_its_seed(ev, offered, tmp_path):
    c = _case(ev, "restart-oom-01")
    run = ev.run_case(c, workdir=tmp_path, llm=ScriptedLLM(_ask_history_then_conclude(c)), strategy="model_loop")
    assert ("knowledge.prior_incidents", c.target, "ok") in run.reads, run.invalid_decisions
    answer = run.model_requests[-1]
    assert f"{len(c.prior_incidents)} prior closed incident(s) of container_restart_loop on {c.target}" in answer
    assert all(p.diagnosis[:60] in answer for p in c.prior_incidents)
    assert run.outcome == "diagnosed"                                 # the open incident is never its own precedent


def test_an_unseeded_case_still_finds_no_precedent(ev, offered, tmp_path):
    c = _case(ev, "dep-cache-stopped")
    assert c.prior_incidents == []
    run = ev.run_case(c, workdir=tmp_path, llm=ScriptedLLM(_ask_history_then_conclude(c)), strategy="model_loop")
    assert ("knowledge.prior_incidents", c.target, "ok") in run.reads
    assert f"no prior closed incident of dependency_unavailable on {c.target}" in run.model_requests[-1]


def test_the_seeds_change_nothing_while_no_class_offers_the_read(ev, tmp_path):
    """The labelled and seeded cases replay as before with a scripted model that reads the cause and concludes."""
    def scripted(case):
        cause, victim = case.label.root_cause, case.target

        def ids(ctx: str, target: str) -> list[str]:
            blocks = re.findall(r'<evidence id="([^"]+)"([^>]*)>\n?([^\n]*)', ctx)
            return [i for i, _, text in blocks if text.startswith(f"{target}: state=")]

        def script(ctx: str):
            if not ids(ctx, cause):
                return {"calls": [("get_container_status", {"target": t}) for t in dict.fromkeys([cause, victim])]}
            cited = ids(ctx, cause)[-1:]
            return {"calls": [("conclude", {"diagnosis": "the labelled cause explains the incident",
                                            "evidence_ids": cited, "confidence": "high", "root_cause_target": cause})]}
        return script
    cases = [c for c in ev.load_cases(CASES) if c.label.expected_hypotheses or c.prior_incidents]
    for c in cases:
        run = ev.run_case(c, workdir=tmp_path / c.id, llm=ScriptedLLM(scripted(c)), strategy="model_loop")
        assert (run.outcome, run.root_cause_target) == ("diagnosed", c.label.root_cause), (c.id, run.invalid_decisions)
        assert not any(r[0] == "knowledge.prior_incidents" for r in run.reads)
        assert READ not in run.model_requests[0]                      # not offered: the model is never told of it
