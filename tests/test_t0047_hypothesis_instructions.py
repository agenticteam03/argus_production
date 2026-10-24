"""T-0047 H4: the hypothesis rules the model is told, made explicit (the analysis of #274's batch).

Three rules the checks already apply (ACR-0024 §3.2) but the instructions left vague: every non-external hypothesis
names its target; `supported` waits until an observation or metric snapshot of that target is in the evidence (a read
requested in the same step is not one yet); evidence ids are copied exactly (one run cited a 15-hex-digit id). Only
the text changes: the checks, the schema, the context slot and the ranking stay as they are.
"""
from __future__ import annotations

from argus.domain.model import Hypothesis, UseReadTools
from argus.orchestration.runner import SLOT_CHARS, hypotheses_slot
from argus.tooling.model_harness import MAX_HYPOTHESES, STATE_TOOL, SYSTEM_PROMPT, ModelHarness
from test_t0047_h1_hypotheses import _view


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_every_non_external_hypothesis_names_its_target():
    assert "Every hypothesis that is not `external` names its target" in _flat(SYSTEM_PROMPT)


def test_supported_waits_for_an_observation_of_its_own_target():
    text = _flat(SYSTEM_PROMPT)
    assert ("Mark one `supported` only once an observation or metric snapshot of its own target is in the evidence"
            in text)
    assert "a read requested in the same step is not one yet: keep it `untested`" in text


def test_evidence_ids_are_copied_exactly():
    assert "Copy evidence IDs exactly as shown" in _flat(SYSTEM_PROMPT)


def test_a_read_steps_list_is_told_the_same_rule_where_it_is_stated():
    tools = {t.name: t for t in ModelHarness(llm=None).tool_definitions(_view_with_reads())}
    assert "`supported` only once a read of its target is in the evidence" in tools[STATE_TOOL].description


def test_the_old_vague_rule_is_gone():
    assert "needs evidence about its own target" not in _flat(SYSTEM_PROMPT)


def test_the_slot_and_the_schema_are_unchanged():
    assert SLOT_CHARS == 1200 and MAX_HYPOTHESES == 5
    d = UseReadTools(calls=[], hypotheses=[Hypothesis(id="h1", statement="the cache is down", cause_class="other",
                                                      target="vm-166/container:argus-lab-cache",
                                                      relation="dependency", status="untested")])
    assert hypotheses_slot([d]) == ("HYPOTHESES UNDER TEST (your latest list; keep the ids, update the statuses):\n"
                                    "- h1 [untested] the cache is down (target vm-166/container:argus-lab-cache; "
                                    "nothing cited)")
    schema = ModelHarness._hypotheses_schema(_view(), ["a", "b"])
    assert schema["items"]["required"] == ["id", "statement", "cause_class", "relation", "status"]


def _view_with_reads():
    from argus.capabilities.catalog import build_catalog
    v = _view()
    v.offered_specs = [s for s in build_catalog() if s.name == "container.status"]
    return v


# --- the labelled cases replay as before with a scripted model --------------------------------------------------------
def _scripted(case):
    """Read the labelled cause's status (and the target's), then conclude on it with a supported, observed one."""
    import re
    cause, victim = case.label.root_cause, case.target

    def ids(ctx: str, target: str) -> list[str]:
        blocks = re.findall(r'<evidence id="([^"]+)"([^>]*)>\n?([^\n]*)', ctx)
        return [i for i, _, text in blocks if text.startswith(f"{target}: state=")]

    def script(ctx: str):
        if not ids(ctx, cause):
            return {"calls": [("get_container_status", {"target": t}) for t in dict.fromkeys([cause, victim])]}
        cited = ids(ctx, cause)[-1:]
        hyps = [{"id": "h1", "statement": "the labelled cause", "cause_class": "other", "target": cause,
                 "relation": "dependency" if cause != victim else "self", "status": "supported", "support": cited}]
        return {"calls": [("conclude", {"diagnosis": "the labelled cause explains the incident",
                                        "evidence_ids": cited, "confidence": "high", "root_cause_target": cause,
                                        "chosen": "h1", "hypotheses": hyps})]}
    return script


def test_the_labelled_cases_replay_as_before(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation as ev
    from argus.adapters.outbound.llm import ScriptedLLM
    from test_core import ROOT
    cases = [c for c in ev.load_cases(ROOT / "tests" / "eval" / "cases")
             if c.label.expected_hypotheses and "/container:" in (c.label.root_cause or "")]
    assert len(cases) == 15                                       # every labelled case (H4 step 1)
    for c in cases:
        run = ev.run_case(c, workdir=tmp_path / c.id, llm=ScriptedLLM(_scripted(c)), strategy="model_loop")
        assert (run.outcome, run.root_cause_target) == ("diagnosed", c.label.root_cause), (c.id, run.invalid_decisions)
        assert run.hypothesis_problems == [] and ev.unsupported_root_cause(run) == 0, (c.id, run.hypothesis_problems)
