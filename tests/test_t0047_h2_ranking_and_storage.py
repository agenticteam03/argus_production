"""T-0047 H2 (ACR-0024 §3.3-§3.5): the hypotheses are ranked by Argus, stored per decision step, and carried to the
next step in the context.

The score is computed in Python from what each cited record is evidence of (`application/ranking.py`, weights in
`config/ranking.yaml`); citing more does not score more. A read step states its list with `state_hypotheses` beside
its read calls; the "Hypotheses under test" slot shows the latest list. `incident_hypothesis` is insert-only.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.application.ranking import Weights, load_ranking, rank, ranking_disagrees
from argus.domain.model import EvidenceRef, Hypothesis, TargetRef, UseReadTools, utcnow
from argus.orchestration.runner import SLOT_CHARS, hypotheses_slot
from argus.orchestration.view import InvestigationView
from argus.ports.ports import ModelReply, ModelToolCall
from argus.tooling.model_harness import STATE_TOOL, ModelHarness
from test_core import FakeMetrics, incident, make_app  # noqa: F401  (make_app is a fixture)

ROOT = Path(__file__).resolve().parents[1]
WORKER = "vm-166/container:argus-lab-worker"
DB = "vm-166/container:argus-lab-db"
HOST = "vm-166/host:vm-166"


def ev(n, target, kind="observation"):
    return EvidenceRef(evidence_id=f"ev{n}", sha256="0" * 64, capability="c", status="ok", model_text="t",
                       target=target, kind=kind)


def h(i, target=WORKER, status="supported", support=(), against=(), relation="self"):
    return Hypothesis(id=f"h{i}", statement=f"hypothesis {i}", cause_class="other", target=target, relation=relation,
                      status=status, support=list(support), against=list(against))


def ranks(hyps, evidence, w=None):
    return {r.id: (r.score, r.rank) for r in rank(hyps, evidence, w)}


# --- the weights (config/ranking.yaml) -------------------------------------------------------------------------------
def test_the_committed_weights_are_the_acr_defaults():
    assert load_ranking(ROOT / "config") == Weights()


def test_a_bad_ranking_file_is_refused(tmp_path):
    good = yaml.safe_load((ROOT / "config" / "ranking.yaml").read_text(encoding="utf-8"))
    for bad, why in (({**good, "extra": 1}, "unknown keys"),
                     ({**good, "weights": {**good["weights"], "alert": -1}}, "≥ 0"),
                     ({**good, "weights": {k: v for k, v in good["weights"].items() if k != "alert"}}, "exactly"),
                     ({**good, "max_target_records": 0}, "integer ≥ 1")):
        (tmp_path / "ranking.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
        with pytest.raises(ValueError, match=why):
            load_ranking(tmp_path)
    assert load_ranking(tmp_path / "missing") == Weights()                       # no file: the defaults


# --- the score and the rank (§3.3) -----------------------------------------------------------------------------------
def test_an_observation_of_its_own_target_outweighs_generic_kinds():
    evidence = [ev(1, WORKER), ev(2, DB), ev(3, WORKER, "alert"), ev(4, WORKER, "metric_snapshot")]
    got = ranks([h(1, support=["ev2", "ev3"]), h(2, support=["ev1"]), h(3, support=["ev4"])], evidence)
    assert got == {"h1": (2.0, 2), "h2": (3.0, 1), "h3": (2.0, 3)}    # a tie: h1 cites two records no other cites, h3 one


def test_citing_every_alert_does_not_score_more():
    evidence = [ev(i, WORKER, "alert") for i in range(1, 6)] + [ev(9, DB)]
    got = ranks([h(1, support=[f"ev{i}" for i in range(1, 6)]), h(2, target=DB, support=["ev9"],
                                                                    relation="dependency")], evidence)
    assert got["h1"] == (1.0, 2) and got["h2"] == (3.0, 1)                       # five alerts count once


def test_own_target_records_count_up_to_the_cap_and_against_subtracts():
    evidence = [ev(i, WORKER) for i in range(1, 6)] + [ev(7, WORKER, "metric_snapshot")]
    got = ranks([h(1, support=[f"ev{i}" for i in range(1, 6)]), h(2, status="ruled_out", support=[],
                                                                    against=["ev7"])], evidence)
    assert got["h1"] == (9.0, 1)                                                 # 3 records x 3, not 5 x 3
    assert got["h2"] == (-2.0, 2)


def test_untested_is_penalised_and_unknown_ids_count_nothing():
    got = ranks([h(1, status="untested"), h(2, support=["ev9"])], [ev(1, WORKER)])
    assert got == {"h1": (-0.5, 2), "h2": (0.0, 1)}


def test_an_external_cause_never_counts_an_observation_as_its_own():
    got = ranks([h(1, target=None, relation="external", support=["ev1"])], [ev(1, WORKER)])
    assert got == {"h1": (1.0, 1)}                                               # another target's: 1, not 3


def test_ties_go_to_the_order_given_and_ranking_disagrees_says_so():
    ranked = rank([h(1), h(2)], [])
    assert [(r.id, r.rank) for r in ranked] == [("h1", 1), ("h2", 2)]
    assert ranking_disagrees(ranked, "h2") and not ranking_disagrees(ranked, "h1")
    assert not ranking_disagrees(ranked, None) and not ranking_disagrees(ranked, "h5")


def test_the_weights_come_from_the_config():
    evidence = [ev(1, WORKER, "alert"), ev(2, WORKER)]
    w = Weights(alert=5.0)
    assert ranks([h(1, support=["ev1"]), h(2, support=["ev2"])], evidence, w) == {"h1": (5.0, 1), "h2": (3.0, 2)}


# --- the store (§3.5) ------------------------------------------------------------------------------------------------
def row(i, rank_=1, chosen=False):
    return {"hypothesis_id": f"h{i}", "statement": "s", "cause_class": "other", "target": WORKER, "relation": "self",
            "status": "supported", "support_ids": ["ev1"], "against_ids": [], "score": 3.0, "rank": rank_,
            "chosen": chosen}


def test_the_sqlite_store_keeps_the_rows_and_refuses_changes(tmp_path):
    store = SqliteStore(str(tmp_path / "h2.db"))
    now = utcnow()
    store.add_hypotheses("inc_1", 2, [row(2, 2), row(1, 1, chosen=True)], now)
    store.add_hypotheses("inc_1", 1, [row(1)], now - timedelta(seconds=5))
    got = store.hypotheses("inc_1")
    assert [(r["step"], r["hypothesis_id"], r["rank"], r["chosen"]) for r in got] == [
        (1, "h1", 1, False), (2, "h1", 1, True), (2, "h2", 2, False)]
    assert got[0]["support_ids"] == ["ev1"] and got[0]["at"] == now - timedelta(seconds=5)
    for sql in ("UPDATE incident_hypothesis SET status = 'ruled_out'", "DELETE FROM incident_hypothesis"):
        with pytest.raises(sqlite3.IntegrityError, match="insert-only"):
            store._q(sql)


# --- a read step states its list (§3.1) ------------------------------------------------------------------------------
def view(max_reads=1):
    from argus.capabilities.catalog import build_catalog
    spec = next(s for s in build_catalog() if s.name == "container.status")
    return InvestigationView(incident=None, incident_class=None, findings=[], passages=[], evidence=[ev(1, WORKER)],
                             decisions_so_far=[], offered_specs=[spec], scope=[TargetRef.parse(WORKER)],
                             steps_left=5, max_reads_per_step=max_reads)


def reply(*calls):
    return ModelReply(text=None, tool_calls=[ModelToolCall(name=n, arguments_json=json.dumps(a)) for n, a in calls],
                      finish_reason="tool_calls")


READ = ("get_container_status", {"target": WORKER})
STATED = (STATE_TOOL, {"hypotheses": [{"id": "h1", "statement": "OOM", "cause_class": "other", "target": WORKER,
                                       "relation": "self", "status": "supported", "support": ["ev1"]}]})


def test_state_hypotheses_is_offered_beside_the_reads_only():
    names = [t.name for t in ModelHarness(llm=None).tool_definitions(view())]
    assert STATE_TOOL in names
    empty = view()
    empty.offered_specs = []
    assert STATE_TOOL not in [t.name for t in ModelHarness(llm=None).tool_definitions(empty)]


def test_a_read_step_carries_its_list_and_the_list_is_not_a_read():
    d = ModelHarness(llm=None).convert(reply(READ, STATED), view(max_reads=1))
    assert isinstance(d, UseReadTools) and len(d.calls) == 1
    assert [x.id for x in d.hypotheses] == ["h1"] and d.hypothesis_problems == []


def test_state_hypotheses_never_stands_alone_or_beside_a_decision():
    harness = ModelHarness(llm=None)
    alone = harness.convert(reply(STATED), view())
    twice = harness.convert(reply(READ, STATED, STATED), view(max_reads=2))
    with_conclude = harness.convert(reply(STATED, ("conclude", {"diagnosis": "x" * 30, "evidence_ids": ["ev1"],
                                                                "confidence": "low"})), view())
    assert (alone.kind, alone.reason) == ("invalid", "malformed")
    assert (twice.kind, twice.reason) == ("invalid", "multiple_calls")
    assert (with_conclude.kind, with_conclude.reason) == ("invalid", "multiple_calls")


def test_a_bad_list_beside_reads_is_reported_not_refused():
    # a read step keeps the structural checks; the evidence checks wait for the decision (test_t0047_hypothesis_check_steps)
    bad = (STATE_TOOL, {"hypotheses": [{"id": "h1", "statement": "x", "cause_class": "other", "target": WORKER,
                                        "relation": "self", "status": "ruled_out", "against": ["ev9"]}]})
    d = ModelHarness(llm=None).convert(reply(READ, bad), view())
    assert isinstance(d, UseReadTools) and d.hypothesis_problems == [
        "h1: cites evidence not stored for this incident: ['ev9']"]


# --- the context slot (§3.4) -----------------------------------------------------------------------------------------
def test_the_slot_shows_the_latest_list_bounded():
    first = UseReadTools(calls=[], hypotheses=[h(1, status="untested")])
    second = UseReadTools(calls=[], hypotheses=[h(1, support=["ev1"]), h(2, status="ruled_out", against=["ev2"])])
    slot = hypotheses_slot([first, second, UseReadTools(calls=[])])               # a later step without a list
    assert slot.startswith("HYPOTHESES UNDER TEST") and "h1 [supported]" in slot and "against ev2" in slot
    assert "untested" not in slot
    assert hypotheses_slot([]) == "" and hypotheses_slot([UseReadTools(calls=[])]) == ""
    long = UseReadTools(calls=[], hypotheses=[Hypothesis(id=f"h{i}", statement="x" * 200, cause_class="other",
                                                         target=WORKER, relation="self", status="untested",
                                                         support=[f"ev{j}" for j in range(9)])
                                             for i in range(1, 6)])
    assert len(hypotheses_slot([long])) <= SLOT_CHARS


# --- both runners: ranked, stored, carried ---------------------------------------------------------------------------
def _script(asked):
    def script(ctx):
        asked.append(ctx)
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        if "container.status" not in ctx:
            return {"calls": [READ, (STATE_TOOL, {"hypotheses": [
                {"id": "h1", "statement": "OOM kill by its limit", "cause_class": "container_restart_loop",
                 "target": WORKER, "relation": "self", "status": "untested"},
                {"id": "h2", "statement": "its database is down", "cause_class": "other", "target": None,
                 "relation": "external", "status": "untested"}]})]}
        return {"calls": [("conclude", {"diagnosis": "OOM-killed by its 64 MiB limit", "evidence_ids": ids[-1:],
                                        "confidence": "high", "root_cause_target": WORKER, "chosen": "h1",
                                        "hypotheses": [
                                            {"id": "h1", "statement": "OOM kill by its limit",
                                             "cause_class": "container_restart_loop", "target": WORKER,
                                             "relation": "self", "status": "supported", "support": ids[-1:]},
                                            {"id": "h2", "statement": "its database is down", "cause_class": "other",
                                             "target": None, "relation": "external", "status": "untested"}]})]}
    return script


@pytest.mark.parametrize("runner", ["plain", "langgraph"])
def test_both_runners_rank_store_and_carry_the_hypotheses(make_app, monkeypatch, runner):
    from argus.adapters.outbound.llm import ScriptedLLM
    from argus.domain.model import IncidentOutcome
    monkeypatch.setenv("ARGUS_RUNNER", runner)
    asked: list[str] = []
    app = make_app(llm=ScriptedLLM(_script(asked)),
                   metrics=FakeMetrics({WORKER: {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137}}))
    inc = app.runner.run(incident(app, WORKER).id)
    assert inc.outcome == IncidentOutcome.diagnosed and inc.root_cause_target == WORKER
    rows = app.store.hypotheses(inc.id)
    assert [(r["step"], r["hypothesis_id"], r["status"], r["rank"], r["chosen"]) for r in rows] == [
        (1, "h1", "untested", 1, False), (1, "h2", "untested", 2, False),
        (2, "h1", "supported", 1, True), (2, "h2", "untested", 2, False)]
    assert rows[2]["score"] == 3.0 and rows[3]["score"] == -0.5
    assert "HYPOTHESES UNDER TEST" in asked[-1] and "h2 [untested]" in asked[-1]  # step 2 saw step 1's list
    assert "HYPOTHESES UNDER TEST" not in asked[0]


def test_a_replayed_step_is_not_stored_twice(make_app):
    app = make_app(metrics=FakeMetrics({}))
    inc = incident(app, WORKER)
    d = UseReadTools(calls=[], hypotheses=[h(1)])
    app.runner._hypotheses(inc, 1, d, [])
    app.runner._hypotheses(inc, 1, d, [])                                        # a run resumed after a crash
    assert len(app.store.hypotheses(inc.id)) == 1
