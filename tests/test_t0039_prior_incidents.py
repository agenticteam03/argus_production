"""T-0039: `query_prior_incidents` (`knowledge.prior_incidents`, ARCHITECTURE §10.5 and §12 Level 3, in-worker,
executor `argus_internal`): during an investigation the model may ask for earlier CLOSED incidents of the same target
and class (`IncidentMemoryPort.similar_incidents`): date, outcome, confidence, root cause and a short diagnosis.
Same target only (host isolation); the incident being investigated is open, so it is never its own precedent.
Offered to no class until measured.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.capabilities.catalog import build_catalog
from argus.capabilities.spec import ExecutorError
from argus.detectors.classes import CLASSES
from argus.domain.model import (Incident, IncidentOutcome, IncidentStatus, RequestKind, TargetRef, TriggerKind,
                                utcnow)
from argus.tooling.executors import KnowledgeClient

ROOT = Path(__file__).resolve().parents[1]
S = {s.name: s for s in build_catalog()}["knowledge.prior_incidents"]
API = TargetRef.parse("vm-166/container:argus-lab-api")
TWIN = TargetRef.parse("vm-095/container:argus-lab-api")            # the same name on the other host


def _inc(store, target, klass, days_ago, closed=True, diagnosis="the cache was stopped", n=[0]):
    n[0] += 1
    t = utcnow() - timedelta(days=days_ago)
    inc = Incident(id=f"inc_prior{n[0]:04d}", target=target, trigger_kind=TriggerKind.alert,
                   request_kind=RequestKind.report, reason="r", principal="p", trigger_id=f"t{n[0]}",
                   incident_class=klass, status=IncidentStatus.closed if closed else IncidentStatus.running,
                   outcome=IncidentOutcome.diagnosed if closed else None, diagnosis=diagnosis if closed else None,
                   confidence="high" if closed else None, root_cause_target="vm-166/container:argus-lab-cache",
                   opened_at=t, closed_at=t + timedelta(minutes=3) if closed else None)
    store.create_incident(inc, None)
    return inc


def test_a_level_3_in_worker_capability_offered_to_no_class():
    assert (S.model_name, S.level, S.safety_class, S.executor, S.runs_in) == (
        "query_prior_incidents", 3, "READ_ONLY_SAFE", "argus_internal", "worker")
    assert set(S.target_kinds) == {"container", "host"}
    assert [c.name for c in CLASSES if S.tags & c.tool_tags] == []
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert pol["capabilities"]["knowledge.prior_incidents"]["max_per_incident"] == 2


def test_closed_incidents_of_the_same_target_and_class_newest_first(tmp_path):
    store = SqliteStore(str(tmp_path / "m.db"))
    old = _inc(store, API, "dependency_unavailable", 5)
    new = _inc(store, API, "dependency_unavailable", 1, diagnosis="the cache container exited (code 137)")
    _inc(store, API, "health_check_failed", 2)                        # another class
    _inc(store, TWIN, "dependency_unavailable", 1)                    # the same name on the other host
    _inc(store, API, "dependency_unavailable", 0, closed=False)       # the open one being investigated
    client = KnowledgeClient(knowledge=None, memory=store)
    r = S.impl(S.args_model(incident_class="dependency_unavailable", k=3), API, None, client)
    assert r.status == "ok" and [x["incident_id"] for x in r.values["incidents"]] == [new.id, old.id]
    assert "2 prior closed incident(s) of dependency_unavailable on vm-166/container:argus-lab-api" in r.model_text
    assert "diagnosed" in r.model_text and "exited (code 137)" in r.model_text
    assert "vm-095" not in r.model_text


def test_none_found_is_said_plainly(tmp_path):
    client = KnowledgeClient(knowledge=None, memory=SqliteStore(str(tmp_path / "m.db")))
    r = S.impl(S.args_model(incident_class="cpu_saturation"), API, None, client)
    assert r.status == "ok" and r.values["incidents"] == [] and "no prior closed incident" in r.model_text


def test_a_long_diagnosis_is_cut_and_k_is_bounded(tmp_path):
    store = SqliteStore(str(tmp_path / "m.db"))
    for d in range(7):
        _inc(store, API, "dependency_unavailable", d + 1, diagnosis="x" * 2000)
    client = KnowledgeClient(knowledge=None, memory=store)
    r = S.impl(S.args_model(incident_class="dependency_unavailable", k=5), API, None, client)
    assert len(r.values["incidents"]) == 5 and all(len(x["diagnosis"]) <= 300 for x in r.values["incidents"])
    with pytest.raises(Exception):
        S.args_model(incident_class="dependency_unavailable", k=6)


def test_an_unknown_class_is_refused():
    r = S.impl(S.args_model(incident_class="made_up_class"), API, None, KnowledgeClient(None, memory=None))
    assert r.status == "error" and r.error_category == "invalid_args"


def test_without_an_incident_memory_the_read_is_unavailable():
    with pytest.raises(ExecutorError):
        KnowledgeClient(knowledge=None).prior_incidents(API, "dependency_unavailable", 3)


def test_the_worker_wiring_gives_the_client_the_store(make_app):
    app = make_app()
    client = app.catalogue.dispatcher.executors.client("argus_internal", "", None)
    assert isinstance(client, KnowledgeClient) and client.memory is app.store


from test_core import make_app  # noqa: E402,F401  (fixture)
