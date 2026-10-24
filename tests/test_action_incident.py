"""Phase 17: reviewed actions come from stored evidence and runbook declarations."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from argus.actions.incident import ActionPolicy
from argus.adapters.inbound.http import build_api
from argus.adapters.outbound.config_adapters import YamlInventory
from argus.domain.model import (AuditRecord, EvidenceRecord, IncidentOutcome, IncidentStatus, Principal,
                                TargetInfo, TargetRef, utcnow)
from test_core import incident, make_app  # noqa: F401  (pytest fixture)

ROOT = Path(__file__).resolve().parent.parent
API = "vm-166/container:argus-lab-api"
CACHE = "vm-166/container:argus-lab-cache"


def _policy():
    policy = ActionPolicy.from_paths(ROOT / "config", ROOT / "argus/runbooks")
    inventory = YamlInventory((ROOT / "config/inventory.yaml").read_text(encoding="utf-8"))
    return policy, inventory


def _status(at, *, state="exited", target=CACHE):
    return EvidenceRecord(
        evidence_id="ev_cache_status", incident_id="inc_sc03", kind="observation",
        capability="container.status", target=target, host="vm-166", executor="docker_read",
        caller="strategy:baseline", source_time=at, collected_at=at, status="ok",
        values={"values": {"state": state}}, model_text=f"state={state}").with_hash()


def test_sc03_candidates_use_stored_root_evidence_and_recalled_runbook():
    policy, inventory = _policy()
    at = utcnow()
    incident = SimpleNamespace(outcome=IncidentOutcome.diagnosed, target=TargetRef.parse(API),
                               root_cause_target=CACHE)
    candidates = policy.next_actions(incident, [_status(at), _status(at, state="running", target=API)],
                                     {"RB-003"}, inventory, now=at)
    assert [(c["action"], c["target"], c["grounds"]) for c in candidates] == [
        ("container.start", CACHE, ["RB-003"])]
    assert candidates[0]["evidence_refs"] == ["ev_cache_status"]
    assert candidates[0]["risk_color"] == "green" and candidates[0]["is_executable"] is False


def test_candidate_is_absent_without_fresh_evidence_or_runbook_recall():
    policy, inventory = _policy()
    at = utcnow()
    incident = SimpleNamespace(outcome=IncidentOutcome.diagnosed, target=TargetRef.parse(API),
                               root_cause_target=CACHE)
    assert policy.next_actions(incident, [_status(at)], set(), inventory, now=at) == []
    assert policy.next_actions(incident, [_status(at - timedelta(minutes=3))], {"RB-003"}, inventory,
                               now=at) == []
    unknown_time = _status(at).model_copy(update={"source_time": None})
    assert policy.next_actions(incident, [unknown_time], {"RB-003"}, inventory, now=at) == []
    assert policy.next_actions(incident, [_status(at, state="running")], {"RB-003"}, inventory,
                               now=at) == []
    victim = SimpleNamespace(outcome=IncidentOutcome.diagnosed, target=TargetRef.parse(API),
                             root_cause_target=API)
    assert policy.next_actions(victim, [_status(at, state="running", target=API)], {"RB-003"}, inventory,
                               now=at) == []


def test_protected_argus_target_is_never_offered_even_with_a_service_card():
    policy, inventory = _policy()
    at = utcnow()
    protected = "vm-095/container:argus-v18-worker"
    cache = inventory.target(TargetRef.parse(CACHE))
    fake_inventory = SimpleNamespace(target=lambda _: TargetInfo(ref=TargetRef.parse(protected),
                                                                  service=cache.service))
    incident = SimpleNamespace(outcome=IncidentOutcome.diagnosed, target=TargetRef.parse(protected),
                               root_cause_target=protected)
    assert policy.next_actions(incident, [_status(at, target=protected)], {"RB-003"}, fake_inventory,
                               now=at) == []


def test_actions_are_never_offered_outside_lab_scope():
    policy, inventory = _policy()
    at = utcnow()
    production = "vm-166/container:production-cache"
    cache = inventory.target(TargetRef.parse(CACHE))
    production_info = TargetInfo(ref=TargetRef.parse(production), scope="production", service=cache.service)
    production_inventory = SimpleNamespace(target=lambda _: production_info)
    incident = SimpleNamespace(outcome=IncidentOutcome.diagnosed, target=TargetRef.parse(production),
                               root_cause_target=production)
    assert policy.next_actions(incident, [_status(at, target=production)], {"RB-003"}, production_inventory,
                               now=at) == []


def test_lab_scope_does_not_override_a_non_lab_target_name():
    policy, inventory = _policy()
    at = utcnow()
    target = "vm-166/container:cache"
    cache = inventory.target(TargetRef.parse(CACHE))
    info = TargetInfo(ref=TargetRef.parse(target), scope="lab", service=cache.service)
    fake_inventory = SimpleNamespace(target=lambda _: info)
    incident = SimpleNamespace(outcome=IncidentOutcome.diagnosed, target=TargetRef.parse(target),
                               root_cause_target=target)
    assert policy.next_actions(incident, [_status(at, target=target)], {"RB-003"}, fake_inventory,
                               now=at) == []


def test_sc03_incident_route_offers_only_grounded_cache_start(make_app):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    inc.incident_class = "dependency_unavailable"
    inc.root_cause_target = CACHE
    inc.outcome, inc.status = IncidentOutcome.diagnosed, IncidentStatus.closed
    app.store.update_incident(inc)
    at = utcnow()
    app.store.append_evidence(EvidenceRecord(
        evidence_id="ev_cache", incident_id=inc.id, kind="observation", capability="container.status",
        target=CACHE, host="vm-166", executor="docker_read", caller="strategy:baseline", source_time=at,
        collected_at=at, status="ok", values={"values": {"state": "exited"}}, model_text="cache exited").with_hash())
    app.store.append(AuditRecord(audit_id=f"recall_{inc.id}", incident_id=inc.id, at=at, category="tool",
                                 event="recall.passages", actor=None,
                                 detail={"passages": [{"runbook_id": "RB-003", "section": "Actions"}]}))
    api = build_api(app)
    route = next(r.endpoint for r in api.routes if getattr(r, "path", None) == "/api/v1/incidents/{incident_id}"
                 and "GET" in getattr(r, "methods", set()))
    body = route(inc.id, Principal(id="alice", kind="human", role="operator"))
    assert [(a["action"], a["target"]) for a in body["next_actions"]] == [("container.start", CACHE)]
    assert body["next_actions"][0]["is_executable"] is False
    viewer_body = route(inc.id, Principal(id="viewer", kind="human", role="viewer"))
    assert viewer_body["next_actions"] == []
