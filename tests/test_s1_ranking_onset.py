"""TASK-50 (scenario 1): a cause whose anomaly started AFTER its dependency's does not rank above the dependency.

The rule is Python, never the model (ACR-0024 §3.3): if hypothesis A's target depends on hypothesis B's target and B's
anomaly onset is earlier than A's, A's own-target evidence does not support A as a cause, A gets one record against, and
B gets one supporting record. The shown text stays "supported by N, contradicted by M"; no percentage.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from argus.application.ranking import Weights, first_onsets, load_ranking, rank
from argus.domain.model import EvidenceRef, Hypothesis

ROOT = Path(__file__).resolve().parents[1]
API = "vm-166/container:argus-lab-api"
CACHE = "vm-166/container:argus-lab-cache"
DEPENDS = {API: [CACHE]}


def ev(n, target, kind="observation"):
    return EvidenceRef(evidence_id=f"ev{n}", sha256="0" * 64, capability="c", status="ok", model_text="t",
                       target=target, kind=kind)


def h(i, target, support=(), against=()):
    return Hypothesis(id=f"h{i}", statement=f"hypothesis {i}", cause_class="other", target=target, relation="self",
                      status="supported", support=list(support), against=list(against))


# the scenario: cache onset t0, API errors t0+60 s, API CPU onset t0+90 s
EVIDENCE = [ev(1, CACHE), ev(2, API), ev(3, API, "metric_snapshot")]
HYPS = [h(1, API, support=["ev2", "ev3"]), h(2, CACHE, support=["ev1"])]


def onsets(api_at, cache_at="2026-10-27T10:00:00Z"):
    return first_onsets([{"target": CACHE, "signal": "dependency_probe_min", "at": cache_at},
                         {"target": API, "signal": "container_cpu_cores", "at": api_at}])


def by_id(ranked):
    return {r.id: r for r in ranked}


def test_without_onsets_the_api_outranks_the_cache():
    r = by_id(rank(HYPS, EVIDENCE))
    assert r["h1"].rank == 1 and r["h2"].rank == 2


def test_cpu_onset_after_the_cache_failure_demotes_the_api():
    r = by_id(rank(HYPS, EVIDENCE, onsets=onsets("2026-10-27T10:01:30Z"), depends_on=DEPENDS))
    assert r["h2"].rank == 1 and r["h1"].rank == 2
    assert (r["h1"].counted_for, r["h1"].counted_against) == (0, 1)      # its own-target records no longer count
    assert (r["h2"].counted_for, r["h2"].counted_against) == (2, 0)      # its own record plus the onset record


def test_cpu_onset_before_the_cache_failure_does_not_demote_the_api():
    r = by_id(rank(HYPS, EVIDENCE, onsets=onsets("2026-10-27T09:59:00Z"), depends_on=DEPENDS))
    assert r["h1"].rank == 1
    assert (r["h1"].counted_for, r["h1"].counted_against) == (2, 0)


def test_the_rule_needs_a_declared_dependency_and_both_onsets():
    late = onsets("2026-10-27T10:01:30Z")
    assert by_id(rank(HYPS, EVIDENCE, onsets=late, depends_on={}))["h1"].rank == 1       # no depends_on
    assert by_id(rank(HYPS, EVIDENCE, onsets=late, depends_on={CACHE: [API]}))["h1"].rank == 1   # wrong direction
    only_api = first_onsets([{"target": API, "signal": "s", "at": "2026-10-27T10:01:30Z"}])
    assert by_id(rank(HYPS, EVIDENCE, onsets=only_api, depends_on=DEPENDS))["h1"].rank == 1  # unknown is not earlier


def test_first_onsets_keeps_the_earliest_per_target_and_skips_bad_times():
    got = first_onsets([{"target": API, "signal": "a", "at": "2026-10-27T10:05:00Z"},
                        {"target": API, "signal": "b", "at": "2026-10-27T10:02:00Z"},
                        {"target": CACHE, "signal": "c", "at": None},
                        {"target": CACHE, "signal": "d", "at": "not a time"}])
    assert list(got) == [API] and got[API].minute == 2


def test_generic_records_of_the_demoted_hypothesis_still_count():
    evidence = EVIDENCE + [ev(4, CACHE, "alert")]
    hyps = [h(1, API, support=["ev2", "ev3", "ev4"]), h(2, CACHE, support=["ev1"])]
    r = by_id(rank(hyps, evidence, onsets=onsets("2026-10-27T10:01:30Z"), depends_on=DEPENDS))
    assert (r["h1"].counted_for, r["h1"].counted_against) == (1, 1)


def test_the_weight_is_data_in_ranking_yaml():
    data = yaml.safe_load((ROOT / "config" / "ranking.yaml").read_text(encoding="utf-8"))
    assert data["weights"]["onset_order"] == Weights().onset_order > 0
    assert load_ranking(ROOT / "config") == Weights()
