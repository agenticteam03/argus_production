"""T-0045 step B4 (ACR-0021): the verdict fields of `GET /api/v1/incidents/{id}` (severity, summary, cause,
evidence_highlights, not_checked, cause_path, duration_ms, next_actions, hypotheses): a pure function of the stored
incident, its class and its evidence. No model call, no host read."""
from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.application.incident_view import build_verdict
from argus.detectors.classes import CLASSES
from argus.domain.model import (AuditRecord, EvidenceRecord, IncidentOutcome, IncidentStatus, TargetRef, utcnow)
from test_core import FakeTargetAgent, incident, make_app  # noqa: F401  (make_app is a fixture)

PASSWORD = "a-long-password"
WORKER = "vm-166/container:argus-lab-worker"
API, CACHE = "vm-166/container:argus-lab-api", "vm-166/container:argus-lab-cache"
SECRET_LINE = "PLANTED-EVIDENCE-LINE-7731"


def spec(name):
    return next(c for c in CLASSES if c.name == name)


def _evidence(app, inc, eid, capability="container.status", target=WORKER, status="ok", text=None):
    app.store.append_evidence(EvidenceRecord(
        evidence_id=eid, incident_id=inc.id, kind="observation", capability=capability, target=target, host="vm-166",
        executor="docker_read", caller="strategy:baseline", source_time=utcnow(), collected_at=utcnow(), status=status,
        values={}, model_text=text or f"{capability} of {target} {SECRET_LINE}\nsecond line").with_hash())


def _diagnosed(app, target, cls, root, diagnosis, confidence="high", findings=(), cited=(), minutes=2):
    inc = incident(app, target)
    inc.incident_class, inc.root_cause_target, inc.diagnosis = cls, root, diagnosis
    inc.confidence, inc.outcome, inc.status = confidence, IncidentOutcome.diagnosed, IncidentStatus.closed
    inc.findings, inc.opened_at = list(findings), utcnow() - timedelta(minutes=minutes + 1)
    inc.closed_at = inc.opened_at + timedelta(minutes=minutes)
    app.store.update_incident(inc)
    app.store.append(AuditRecord(audit_id=f"aud_{inc.id}", incident_id=inc.id, at=utcnow(), category="incident",
                                 event="incident.recorded", actor=None,
                                 detail={"cited": list(cited), "outcome": "diagnosed", "root_cause_target": root,
                                         "status": "closed"}))
    return inc


def _verdict(app, inc, show=True):
    stored = app.store.get_incident(inc.id)
    cited = [e for a in app.store.list_for(inc.id) if a.event == "incident.recorded" for e in a.detail.get("cited", [])]
    depends = {str(t.ref): [str(d) for d in t.depends_on] for t in app.inventory.targets()}
    return build_verdict(stored, next((c for c in CLASSES if c.name == stored.incident_class), None),
                         app.store.list_evidence(inc.id), cited, depends, show)


# --- the class severity -----------------------------------------------------------------------------------------------
def test_class_severities():
    assert {c.name: c.severity for c in CLASSES} == {
        "container_restart_loop": "critical", "dependency_unavailable": "critical", "health_check_failed": "critical",
        "nginx_upstream_failure": "critical", "postgresql_connection_exhaustion": "critical",
        "cpu_saturation": "critical", "disk_pressure": "critical", "monitoring_blind_spot": "warning"}


# --- an SC-01-like incident (restart loop, OOM) -----------------------------------------------------------------------
def test_an_sc01_like_incident_has_every_field(make_app):
    app = make_app()
    inc = _diagnosed(app, WORKER, "container_restart_loop", WORKER, "OOM-killed by its 64 MiB limit. It restarts.",
                     findings=["4 restarts in the last 10 minutes", "last exit OOMKilled=True"], cited=["ev_a", "ev_b"])
    _evidence(app, inc, "ev_a")
    _evidence(app, inc, "ev_b", capability="metrics.container_history")
    _evidence(app, inc, "ev_c", capability="logs.tail", status="timeout")
    v = _verdict(app, inc)
    assert v["severity"] == "critical"
    assert "4 restarts" in v["summary"] and "argus-lab-worker" in v["summary"]
    assert v["cause"] == {"target": WORKER, "kind": "restart_loop", "statement": "OOM-killed by its 64 MiB limit.",
                          "confidence": 0.9, "confidence_label": "High"}
    assert [h["evidence_id"] for h in v["evidence_highlights"]] == ["ev_a", "ev_b"]
    assert all(h["stance"] == "supports" and SECRET_LINE in h["text"] and "\n" not in h["text"]
               for h in v["evidence_highlights"])
    assert v["not_checked"] == ["logs.tail on vm-166/container:argus-lab-worker · timeout"]
    assert v["cause_path"] == [WORKER]
    assert 110_000 <= v["duration_ms"] <= 130_000
    assert v["next_actions"] == [] and v["hypotheses"] == []


# --- an SC-03-like incident (a dependency) ------------------------------------------------------------------------------
def test_an_sc03_like_incident_names_the_cause_and_the_path(make_app):
    app = make_app()
    inc = _diagnosed(app, API, "dependency_unavailable", CACHE, "argus-lab-cache is stopped.", confidence="medium",
                     findings=["at least one declared dependency probe is failing"], cited=["ev_1"])
    _evidence(app, inc, "ev_1", target=CACHE)
    v = _verdict(app, inc)
    assert v["cause_path"] == [API, CACHE]
    assert v["cause"]["confidence"] == 0.6 and v["cause"]["confidence_label"] == "Medium" and v["cause"]["kind"] == "dependency"
    assert "dependency" in v["summary"].lower() and "argus-lab-api" in v["summary"]


# --- an undiagnosable incident --------------------------------------------------------------------------------------------
def test_an_undiagnosable_incident_says_what_could_not_be_checked(make_app):
    app = make_app()
    inc = _diagnosed(app, WORKER, "container_restart_loop", None, "", confidence=None,
                     findings=["signal missing (unknown, not healthy): restarts_10m"])
    inc.outcome, inc.diagnosis = IncidentOutcome.undiagnosable, None
    app.store.update_incident(inc)
    _evidence(app, inc, "ev_x", status="error")
    v = _verdict(app, inc)
    assert v["severity"] == "warning" and v["cause"] is None and v["cause_path"] == []
    assert "could not" in v["summary"].lower()
    assert v["evidence_highlights"] == []
    assert "restarts_10m" in " ".join(v["not_checked"]) and "container.status on" in " ".join(v["not_checked"])


def test_no_incident_is_ok_and_an_unsupported_one_is_a_warning(make_app):
    app = make_app()
    ok, odd = incident(app, WORKER), incident(app, WORKER)
    ok.outcome, odd.outcome, odd.incident_class = IncidentOutcome.no_incident, IncidentOutcome.unsupported_escalated, None
    app.store.update_incident(ok)
    app.store.update_incident(odd)
    assert _verdict(app, ok)["severity"] == "ok" and "healthy" in _verdict(app, ok)["summary"].lower()
    v = _verdict(app, odd)
    assert v["severity"] == "warning" and "not covered" in v["summary"].lower()


def test_an_old_incident_without_a_class_still_answers_with_defaults(make_app):
    app = make_app()
    inc = incident(app, WORKER)                                  # queued: no class, outcome, diagnosis or close
    v = _verdict(app, inc)
    assert v["severity"] is None and v["cause"] is None and v["cause_path"] == [] and v["duration_ms"] is None
    assert isinstance(v["summary"], str) and v["evidence_highlights"] == [] and v["not_checked"] == []


def test_the_runners_class_prefix_is_not_shown_and_a_metrics_outage_is_not_checked(make_app):
    app = make_app()
    inc = _diagnosed(app, WORKER, "container_restart_loop", WORKER, "Because.",
                     findings=["container_restart_loop: 5 restarts in the last 10 minutes", "also matched: health_check_failed"])
    assert _verdict(app, inc)["summary"] == "Restart loop on argus-lab-worker: 5 restarts in the last 10 minutes"
    down = _diagnosed(app, WORKER, None, None, "", confidence=None,
                      findings=["metrics stale or unavailable: prometheus at <a host>: ConnectError",
                                "container_restart_loop: signal missing (unknown, not healthy): oom_killed"])
    down.outcome = IncidentOutcome.undiagnosable
    app.store.update_incident(down)
    assert _verdict(app, down)["not_checked"] == ["metrics · stale or unavailable"]
    assert "ConnectError" not in json.dumps(_verdict(app, down))


def test_the_summary_falls_back_to_the_first_sentence_of_the_diagnosis(make_app):
    app = make_app()
    inc = _diagnosed(app, WORKER, "container_restart_loop", WORKER, "Crashes at startup. Details follow.", findings=[])
    assert _verdict(app, inc)["summary"] == "Crashes at startup."


def test_every_class_has_a_summary(make_app):
    app = make_app()
    for c in CLASSES:
        target = "vm-166/host:vm-166" if "host" in c.target_kinds else WORKER
        inc = _diagnosed(app, target, c.name, target, "Because.", findings=["a finding"])
        assert _verdict(app, inc)["summary"] and _verdict(app, inc)["cause"]["kind"], c.name


# --- the route: role redaction and leaks --------------------------------------------------------------------------------
def _client(app, role):
    app.store.upsert_principal("alice", "human", role, ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = TestClient(build_api(app))
    token = api.post("/api/v1/auth/token", data={"username": "alice", "password": PASSWORD, "scope": "read"}).json()["access_token"]
    return api, {"Authorization": f"Bearer {token}"}


def test_a_viewer_gets_the_verdict_but_no_evidence_text(make_app):
    app = make_app()
    inc = _diagnosed(app, WORKER, "container_restart_loop", WORKER, "OOM-killed.", findings=["4 restarts"], cited=["ev_a"])
    _evidence(app, inc, "ev_a")
    _evidence(app, inc, "ev_b", status="timeout")
    api, h = _client(app, "viewer")
    body = api.get(f"/api/v1/incidents/{inc.id}", headers=h).json()
    assert body["severity"] == "critical" and body["cause"]["target"] == WORKER
    assert body["evidence_highlights"] == [] and "evidence" not in body
    assert SECRET_LINE not in json.dumps(body)
    assert body["not_checked"] == [f"container.status on {WORKER} · timeout"]


def test_an_operator_gets_the_highlights_and_nothing_leaks(make_app):
    app = make_app()
    inc = _diagnosed(app, WORKER, "container_restart_loop", WORKER, "OOM-killed.", findings=["4 restarts"], cited=["ev_a"])
    _evidence(app, inc, "ev_a")
    api, h = _client(app, "operator")
    body = api.get(f"/api/v1/incidents/{inc.id}", headers=h).json()
    assert body["evidence_highlights"][0]["text"].endswith(SECRET_LINE)
    text = json.dumps({k: v for k, v in body.items() if k in ("summary", "cause", "not_checked", "cause_path")})
    assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) and "://" not in text
    assert FakeTargetAgent.calls == []                           # derived from the store alone
