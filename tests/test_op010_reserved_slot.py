"""OP-010: the db-probe keeps a connection slot of its own (PostgreSQL 16 `reserved_connections` +
`pg_use_reserved_connections`), so a leak that takes every ordinary slot cannot blind it.

The lab database reserves one slot and grants the monitoring role; the probe reports whether its role really has
such a slot (`monitor_slot_reserved`), so a real database without the prerequisite is visible, not silently blind.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from test_db_probe import FakeConn, _db_probe

ROOT = Path(__file__).resolve().parents[1]


def _lab():
    return yaml.safe_load((ROOT / "deploy" / "lab" / "compose.lab.yml").read_text(encoding="utf-8"))["services"]


class ReservedConn(FakeConn):
    """Postgres 16 with one slot reserved for roles granted pg_use_reserved_connections; the probe's role is one."""

    def __init__(self, svc, member=True, reserved="1"):
        super().__init__(svc)
        self.member, self.reserved = member, reserved

    def run(self, sql):
        q = self.svc.DB_QUERIES
        if sql == q["settings"]:
            self.statements.append(sql)
            return [["max_connections", "20"], ["superuser_reserved_connections", "3"],
                    ["reserved_connections", self.reserved]]
        if sql == q["reserved_slot"]:
            self.statements.append(sql)
            return [[1 if self.member else 0]]
        return super().run(sql)


def test_lab_database_reserves_a_slot_for_the_monitoring_role():
    db = _lab()["argus-lab-db"]
    assert "reserved_connections=1" in " ".join(db["command"])
    init = (ROOT / "deploy" / "lab" / "db-init" / "10-argus-monitor.sh").read_text(encoding="utf-8")
    assert "GRANT pg_use_reserved_connections TO argus_monitor" in init
    assert "pg_use_reserved_connections TO argus_lab_app" not in init          # the leaker's role must not get it


def test_sc04_leaker_defaults_below_the_limit_and_can_take_every_ordinary_slot():
    s = _lab()["argus-lab-leaker"]
    raw = s["environment"]["SESSIONS"]
    assert raw == "${SC04_SESSIONS:-15}"                    # 15 of 16 usable = 94 %; SC04_SESSIONS=16 runs at 100 %
    assert s["pids_limit"] >= 3 * 16 + 8 and int(s["mem_limit"].rstrip("m")) >= 8 * 16    # sized for the 100 % run


def test_db_probe_counts_the_extra_reserved_slot_and_reports_it_as_the_monitors(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "pg_connect", lambda db: ReservedConn(svc))
    d = svc.db_probe(["database", "health"], {"name": ["argus-lab-db"]})
    assert (d["reserved_connections"], d["usable_connections"]) == (4, 16)
    assert d["monitor_slot_reserved"] is True
    assert "argus_db_monitor_slot_reserved{container=\"argus-lab-db\"} 1" in svc.db_metrics()


def test_db_probe_reports_a_database_without_the_prerequisite(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)
    for conn in (lambda: ReservedConn(svc, member=False), lambda: ReservedConn(svc, reserved="0")):
        monkeypatch.setattr(svc, "pg_connect", lambda db, c=conn: c())
        assert svc.db_probe(["database", "health"], {"name": ["argus-lab-db"]})["monitor_slot_reserved"] is False
        assert "argus_db_monitor_slot_reserved{container=\"argus-lab-db\"} 0" in svc.db_metrics()


def test_the_reserved_slot_query_reads_only_the_role_catalog(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)
    sql = svc.DB_QUERIES["reserved_slot"]
    assert sql.lstrip().upper().startswith("SELECT") and "pg_roles" in sql
    assert "pg_use_reserved_connections" in sql and "pg_has_role" in sql     # absent on PG < 16: 0 rows, no error


def test_database_health_text_warns_when_the_monitoring_slot_is_not_reserved():
    from argus.capabilities.catalog import NoArgs, db_health
    from argus.domain.model import TargetInfo, TargetRef

    def client(reserved):
        class C:
            def get(self, path, params=None):
                return {"database": "argus-lab-db", "ok": True, "max_connections": 20, "reserved_connections": 3,
                        "usable_connections": 17, "client_connections": 1, "usage_percent": 5.9, "by_state": {},
                        "by_client": [], "longest_transactions": [], "lock_waits": 0, "blocked_sessions": 0,
                        "monitor_slot_reserved": reserved, "collected_at": "2026-10-08T16:00:00+00:00"}
        return C()

    ref = TargetRef.parse("vm-166/container:argus-lab-db")
    info = TargetInfo(ref=ref, database="argus_lab")
    assert "monitoring slot not reserved" in db_health(NoArgs(), ref, info, client(False)).model_text
    assert "monitoring slot not reserved" not in db_health(NoArgs(), ref, info, client(True)).model_text
