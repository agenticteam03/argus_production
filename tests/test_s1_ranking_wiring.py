"""TASK-62 (scenario 1): the live ranking path uses TASK-50's onset rule.

`SkeletonRunner._hypotheses` (GraphRunner inherits it) reads the incident's `analysis.anomaly_summary` onsets and the
inventory's direct dependencies and passes both to `rank()`. Without an anomaly_summary the call is the old one.
"""
from __future__ import annotations

from datetime import datetime, timezone

from argus.domain.model import EvidenceRecord, EvidenceRef, Hypothesis, Incident, TargetInfo, TargetRef, UseReadTools
from argus.orchestration.graph_runner import GraphRunner
from argus.orchestration.runner import SkeletonRunner

API = "vm-166/container:argus-lab-api"
CACHE = "vm-166/container:argus-lab-cache"
NOW = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)


class Memory:
    def __init__(self, records):
        self.records, self.rows = {r.evidence_id: r for r in records}, []

    def hypotheses(self, incident_id):
        return []

    def add_hypotheses(self, incident_id, step, rows, at):
        self.rows = rows

    def get_evidence(self, ids):
        return [self.records[i] for i in ids if i in self.records]


class Inventory:
    def target(self, ref):
        return TargetInfo(ref=ref, depends_on=[TargetRef.parse(CACHE)] if str(ref) == API else [])


def rec(i, target, kind="observation", capability=None, values=None):
    return EvidenceRecord(evidence_id=f"ev{i}", incident_id="inc1", kind=kind, capability=capability, target=target,
                          host="vm-166", executor=None, caller="model", source_time=None, collected_at=NOW,
                          status="ok", values=values or {}, model_text="t")


def ref(r):
    return EvidenceRef(evidence_id=r.evidence_id, sha256="0" * 64, capability=r.capability, status="ok",
                       model_text="t", target=r.target, kind=r.kind)


def onsets(api_at):
    return {"onsets": [{"target": CACHE, "signal": "dependency_probe_min", "at": "2026-10-27T10:00:00Z"},
                       {"target": API, "signal": "container_cpu_cores", "at": api_at}]}


def run(cls, with_summary, api_at="2026-10-27T10:01:30Z"):
    records = [rec(1, CACHE), rec(2, API), rec(3, API, "metric_snapshot")]
    if with_summary:
        records.append(rec(4, API, capability="analysis.anomaly_summary", values=onsets(api_at)))
    runner = cls.__new__(cls)
    runner.memory, runner.inventory, runner.ranking = Memory(records), Inventory(), None
    hyps = [Hypothesis(id="h1", statement="api", cause_class="other", target=API, relation="self", status="supported",
                       support=["ev2", "ev3"]),
            Hypothesis(id="h2", statement="cache", cause_class="other", target=CACHE, relation="dependency",
                       status="supported", support=["ev1"])]
    inc = Incident.model_construct(id="inc1")
    runner._hypotheses(inc, 1, UseReadTools(calls=[], hypotheses=hyps), [ref(r) for r in records])
    return {r["hypothesis_id"]: r["rank"] for r in runner.memory.rows}


def test_with_the_scenario_onsets_the_cache_ranks_first_in_both_runners():
    for cls in (SkeletonRunner, GraphRunner):
        assert run(cls, True) == {"h1": 2, "h2": 1}, cls


def test_without_an_anomaly_summary_the_order_is_the_old_order():
    for cls in (SkeletonRunner, GraphRunner):
        assert run(cls, False) == {"h1": 1, "h2": 2}, cls


def test_an_api_onset_before_the_cache_failure_changes_nothing():
    assert run(SkeletonRunner, True, api_at="2026-10-27T09:59:00Z") == {"h1": 1, "h2": 2}
