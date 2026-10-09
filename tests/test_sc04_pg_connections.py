"""T-0020 / SC-04: PostgreSQL connection exhaustion (class `postgresql_connection_exhaustion`, RB-004).

The db-probe publishes the slot usage of each allowlisted database on `/metrics` (token-protected); vm-166's
Prometheus scrapes it; the signal `db_connection_usage` is the ratio sustained for 5 minutes (RB-004's calibration
default); the detector opens the class at 90 %. A database that cannot be read is unknown, never healthy (G-007).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, MetricSnapshot, TargetRef, utcnow

from test_core import FakeMetrics, incident, make_app  # noqa: F401  (make_app is a fixture)
from test_db_probe import FakeConn, _db_probe

ROOT = Path(__file__).resolve().parents[1]
DB = "vm-166/container:argus-lab-db"
LEAKER = "vm-166/container:argus-lab-leaker"


# --- the probe's metrics --------------------------------------------------------------------------
def test_db_probe_metrics_publish_slot_usage_per_database(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)
    conn = FakeConn(svc)
    monkeypatch.setattr(svc, "pg_connect", lambda db: conn)
    text = svc.db_metrics()
    lab = 'container="argus-lab-db"'
    for line in (f"argus_db_up{{{lab}}} 1", f"argus_db_connections_max{{{lab}}} 20",
                 f"argus_db_connections_usable{{{lab}}} 17", f"argus_db_connections_used{{{lab}}} 14",
                 f'argus_db_connections{{{lab},state="idle in transaction"}} 3',
                 f"argus_db_oldest_xact_seconds{{{lab}}} 912.5", f"argus_db_lock_waits{{{lab}}} 1"):
        assert line in text.splitlines(), line
    assert "query" not in text and conn.closed


def test_db_probe_metrics_of_an_unreadable_database_are_unknown_not_zero(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)

    def refuse(db):
        raise ConnectionRefusedError("too many clients")
    monkeypatch.setattr(svc, "pg_connect", refuse)
    lines = [ln for ln in svc.db_metrics().splitlines() if ln and not ln.startswith("#")]
    assert lines == ['argus_db_up{container="argus-lab-db"} 0']          # no used/usable series at all


def test_db_probe_metrics_of_a_query_that_fails_after_connecting_are_unknown_not_a_500(tmp_path, monkeypatch):
    """Review of PR #38: the 3 s statement_timeout on a busy database, or a lost connection, must not turn the whole
    scrape into a 500 (no `argus_db_*` series at all: "not a database"). It is `argus_db_up 0`, and the connection
    is still closed."""
    svc = _db_probe(tmp_path, monkeypatch)
    conn = FakeConn(svc)

    def timeout(sql):
        if sql.startswith("SET"):
            return []
        raise TimeoutError("canceling statement due to statement timeout")
    conn.run = timeout
    monkeypatch.setattr(svc, "pg_connect", lambda db: conn)
    lines = [ln for ln in svc.db_metrics().splitlines() if ln and not ln.startswith("#")]
    assert lines == ['argus_db_up{container="argus-lab-db"} 0'] and conn.closed


# --- Prometheus, signal, alert ------------------------------------------------------------------------
def test_vm166_prometheus_scrapes_the_db_probe_with_its_token():
    p166 = yaml.safe_load((ROOT / "deploy" / "monitoring" / "prometheus-vm-166.yml").read_text(encoding="utf-8"))
    job = next(j for j in p166["scrape_configs"] if j["job_name"] == "argus-v18-db-probe")
    assert job["static_configs"] == [{"targets": ["argus-v18-db-probe:8700"], "labels": {"argus_host": "vm-166"}}]
    assert job["authorization"] == {"type": "Bearer", "credentials_file": "/etc/prometheus/secrets/db_probe_token"}
    p095 = yaml.safe_load((ROOT / "deploy" / "monitoring" / "prometheus-vm-095.yml").read_text(encoding="utf-8"))
    assert all(j["job_name"] != "argus-v18-db-probe" for j in p095["scrape_configs"])
    mon = yaml.safe_load((ROOT / "deploy" / "monitoring" / "compose.monitoring.yml").read_text(encoding="utf-8"))
    assert "/opt/argus-v18/secrets/prometheus:/etc/prometheus/secrets:ro" in mon["services"]["argus-v18-prometheus"]["volumes"]


def test_signals_and_alert_for_connection_exhaustion():
    sig = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
    used = 'argus_db_connections_used{argus_host="$host",container="$name"}'
    usable = 'argus_db_connections_usable{argus_host="$host",container="$name"}'
    assert sig["db_connection_usage"] == f"min_over_time(({used} / ({usable} > 0))[5m:30s])"
    assert sig["db_up"] == 'argus_db_up{argus_host="$host",container="$name"}'
    rules = yaml.safe_load((ROOT / "deploy" / "monitoring" / "alerts.yml").read_text(encoding="utf-8"))
    alert = next(r for g in rules["groups"] for r in g["rules"] if r.get("alert") == "DbConnectionsExhausted")
    assert alert["expr"] == "argus_db_connections_used / (argus_db_connections_usable > 0) >= 0.9"
    assert alert["for"] == "5m"


# --- the detector and the class -------------------------------------------------------------------------
def _snap(**values):
    return MetricSnapshot(target=TargetRef.parse(DB), observed_at=utcnow(), values=values)


def test_detector_matches_at_ninety_percent_sustained():
    from argus.detectors.classes import postgresql_connection_exhaustion as det
    r = det(_snap(db_up=1, db_connection_usage=0.941))
    assert r.matched and any("94%" in f for f in r.findings)
    assert not det(_snap(db_up=1, db_connection_usage=0.5)).matched


def test_detector_treats_missing_or_unreadable_as_unknown():
    from argus.detectors.classes import postgresql_connection_exhaustion as det
    r = det(_snap(db_up=None, db_connection_usage=None))              # not a database: silent
    assert not r.matched and r.findings == []
    r = det(_snap(db_up=0, db_connection_usage=None))
    assert not r.matched and any("unknown" in f for f in r.findings)
    r = det(_snap(db_up=1, db_connection_usage=None))
    assert not r.matched and any("unknown" in f for f in r.findings)


def test_the_class_is_registered_with_rb004():
    from argus.detectors.classes import CLASSES
    c = next(c for c in CLASSES if c.name == "postgresql_connection_exhaustion")
    assert (c.family, c.runbook_ids, c.branch_runbook_ids, c.strategy) == ("database", ["RB-004"], ["RB-013"], "model_loop")
    assert c.required_signals == {"db_connection_usage", "db_up"}
    assert {"database", "knowledge", "logs", "container"} <= c.tool_tags


def test_scripted_diagnosis_reads_the_database_and_names_the_leaker(make_app):
    def script(ctx: str):
        if "client connections" not in ctx:                         # database.health not read yet
            return {"calls": [("inspect_database_health", {"target": DB})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "argus-lab-leaker holds idle-in-transaction sessions (RB-004 H3)",
                                        "evidence_ids": ids[-1:], "confidence": "medium",
                                        "root_cause_target": LEAKER})]}
    app = make_app(llm=ScriptedLLM(script), metrics=FakeMetrics({DB: {"db_up": 1, "db_connection_usage": 0.94}}))
    inc = app.runner.run(incident(app, DB, reason="clients cannot get a database connection").id)
    assert inc.incident_class == "postgresql_connection_exhaustion" and inc.outcome == IncidentOutcome.diagnosed
    assert "database.health" in [e.capability for e in app.store.list_evidence(inc.id)]


# --- runbook, capability, inventory, lab ----------------------------------------------------------------
def test_rb004_names_its_detector_and_is_bumped():
    text = (ROOT / "argus" / "runbooks" / "RB-004-postgresql-connection-exhaustion.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(re.search(r"```yaml\n(.*?)```", text, re.S).group(1))
    assert meta["detector"] == "postgresql_connection_exhaustion"
    assert meta["version"] == "1.0.2" and str(meta["last_reviewed"]) == "2026-10-07"
    assert str(meta["last_tested"]) == "2026-10-07"                       # SC-04 run 2 (inc_075fb0006098)


def test_database_health_is_read_only_sensitive_as_rb004_says():
    from argus.capabilities.catalog import build_catalog
    spec = next(s for s in build_catalog() if s.name == "database.health")
    assert spec.safety_class == "READ_ONLY_SENSITIVE"


def test_inventory_declares_the_leaker_and_the_database_port():
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    t = {x["ref"]: x for x in inv["targets"]}
    assert t[DB]["tcp_ports"] == [5432]
    assert t[LEAKER]["depends_on"] == [DB]


def test_sc04_leaker_is_a_bounded_lab_workload():
    lab = yaml.safe_load((ROOT / "deploy" / "lab" / "compose.lab.yml").read_text(encoding="utf-8"))
    s = lab["services"]["argus-lab-leaker"]
    assert s["image"] == "postgres:16-alpine" and s["profiles"] == ["sc04"]
    assert s["mem_limit"] and s["cpus"] and s["pids_limit"] and "ports" not in s
    assert s["networks"] == ["argus-lab-app"] and s["environment"]["PGAPPNAME"] == "argus-lab-leaker"
    # SC-04 run 1: "can't fork" at pids_limit 32 - each session costs a subshell, sleep and psql (~3 processes, ~5 MiB)
    sessions = 16                                      # OP-010: sized for SC04_SESSIONS=16 (every ordinary slot)
    assert s["pids_limit"] >= 3 * sessions + 8
    assert int(s["mem_limit"].rstrip("m")) >= 8 * sessions
    # SC-04 run 2: the image declares VOLUME /var/lib/postgresql/data, so each start left an anonymous volume that
    # nonint-check reported as a non-Argus difference; a tmpfs there means no volume at all
    assert "/var/lib/postgresql/data" in s["tmpfs"]
    assert any("app_password" in v for v in s["volumes"])
    script = (ROOT / "deploy" / "lab" / "workloads" / "leaker.sh").read_text(encoding="utf-8")
    assert "BEGIN" in script and "SESSIONS:-15" in script and "\r\n" not in script
    init = (ROOT / "deploy" / "lab" / "db-init" / "10-argus-monitor.sh").read_text(encoding="utf-8")
    assert "CREATE ROLE argus_lab_app LOGIN" in init
