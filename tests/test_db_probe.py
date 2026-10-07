"""T-0019 batch 1: the database probe (ARCHITECTURE §4.6 `db-probe`) and `database.health` (§12.2, Level 3).

The probe runs on the target host with a read-only monitoring role. It reads only system views (pg_stat_activity,
pg_locks, pg_settings), never business rows and never SQL text. Argus reaches it through the `db_probe` executor
like every other probe: policy, audit and evidence go through InvokeCapability.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

from argus.application.invoke_capability import InvocationContext
from argus.capabilities.spec import ExecutorError

from test_core import FakeTargetAgent, incident, make_app  # noqa: F401  (make_app is a fixture)

ROOT = Path(__file__).resolve().parents[1]
DB = "vm-166/container:argus-lab-db"
DB_CFG = {"name": "argus-lab-db", "host": "argus-lab-db", "port": 5432, "dbname": "argus_lab"}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db_probe(tmp_path, monkeypatch):
    cfg = tmp_path / "target.json"
    cfg.write_bytes(json.dumps({"host": "vm-166", "containers": ["argus-lab-db"], "databases": [DB_CFG]}).encode())
    (tmp_path / "db_probe_token").write_bytes(b"t0ken")
    monkeypatch.setenv("ROLE", "db_probe")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    monkeypatch.setenv("TA_SECRETS", str(tmp_path))
    return _load("ta_service_db", ROOT / "services" / "target" / "service.py")


class FakeConn:
    """Answers the probe's named queries like pg8000.native.Connection.run, and records every statement."""

    def __init__(self, svc):
        self.svc, self.statements, self.closed = svc, [], False

    def run(self, sql):
        self.statements.append(sql)
        q = self.svc.DB_QUERIES
        if sql == q["settings"]:
            return [["max_connections", "20"], ["superuser_reserved_connections", "3"], ["reserved_connections", "0"]]
        if sql == q["by_state"]:
            return [["active", 2], ["idle", 9], ["idle in transaction", 3]]
        if sql == q["by_client"]:
            return [["shop-api", "shop", 12], ["(none)", "postgres", 2]]
        if sql == q["longest"]:
            return [[4242, "shop-api", "idle in transaction", "Client", "ClientRead", 912.5]]
        if sql == q["locks"]:
            return [[1, 1]]
        return []                                           # SET statements

    def close(self):
        self.closed = True


# --- the probe (services/target/service.py, ROLE=db_probe) ---------------------------------------
def test_db_probe_reads_only_system_views_and_never_sql_text(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)
    assert set(svc.DB_QUERIES) == {"settings", "by_state", "by_client", "longest", "locks"}
    for name, sql in svc.DB_QUERIES.items():
        tables = re.findall(r"\b(?:FROM|JOIN)\s+([a-z_]+)\b(?!\s*\()", sql, flags=re.I)   # not now()
        assert tables and all(t in ("pg_stat_activity", "pg_locks", "pg_settings") for t in tables), (name, tables)
        assert not re.search(r"\bquery\b", sql, flags=re.I), f"{name} selects SQL text"
        assert sql.lstrip().upper().startswith("SELECT"), name


def test_db_probe_summarises_connections_clients_transactions_and_locks(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)
    conn = FakeConn(svc)
    monkeypatch.setattr(svc, "pg_connect", lambda db: conn)
    d = svc.db_probe(["database", "health"], {"name": ["argus-lab-db"]})
    assert d["database"] == "argus-lab-db" and d["ok"] is True
    assert (d["max_connections"], d["reserved_connections"], d["usable_connections"]) == (20, 3, 17)
    assert d["client_connections"] == 14 and d["usage_percent"] == 82.4
    assert d["by_state"] == {"active": 2, "idle": 9, "idle in transaction": 3}
    assert d["by_client"][0] == {"application_name": "shop-api", "role": "shop", "connections": 12}
    assert d["longest_transactions"][0] == {"pid": 4242, "application_name": "shop-api", "state": "idle in transaction",
                                            "wait_event_type": "Client", "wait_event": "ClientRead", "age_s": 912.5}
    assert (d["lock_waits"], d["blocked_sessions"]) == (1, 1)
    assert "query" not in json.dumps(d)
    # the session is read-only and bounded before any query, and always closed
    assert conn.statements[0] == "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
    assert conn.statements[1].startswith("SET statement_timeout")
    assert conn.closed


def test_db_probe_refuses_a_database_outside_its_allowlist(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "pg_connect", lambda db: pytest.fail("must not connect"))
    with pytest.raises(svc.Err) as e:
        svc.db_probe(["database", "health"], {"name": ["postgres-prod"]})
    assert e.value.code == 400
    with pytest.raises(svc.Err) as e:
        svc.db_probe(["database", "rows"], {"name": ["argus-lab-db"]})
    assert e.value.code == 404


def test_db_probe_unreachable_database_is_an_error_not_zero(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)

    def refuse(db):
        raise ConnectionRefusedError("refused")
    monkeypatch.setattr(svc, "pg_connect", refuse)
    with pytest.raises(svc.Err) as e:
        svc.db_probe(["database", "health"], {"name": ["argus-lab-db"]})
    assert e.value.code == 502 and "ConnectionRefusedError" in e.value.msg


def test_db_probe_has_its_own_token(tmp_path, monkeypatch):
    svc = _db_probe(tmp_path, monkeypatch)
    assert svc.TOKEN_NAME == "db_probe" and svc.TOKEN == "t0ken"
    assert svc.ROUTES["db_probe"] is svc.db_probe


# --- configuration: inventory → rendered allowlist, policy, executors ----------------------------
def test_inventory_declares_the_lab_database_and_its_probe():
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    assert inv["hosts"]["vm-166"]["executors"]["db_probe"] == "http://argus-v18-tunnel:18704"
    assert "db_probe" not in inv["hosts"]["vm-095"]["executors"]
    db = next(t for t in inv["targets"] if t["ref"] == DB)
    assert db["database"] == {"dbname": "argus_lab", "port": 5432}


def test_rendered_vm166_config_lists_the_database(tmp_path):
    render = _load("render_cfg", ROOT / "ops" / "render_target_config.py")
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    assert render.render_host(inv, "vm-166")["databases"] == [DB_CFG]
    assert render.render_host(inv, "vm-095")["databases"] == []
    committed = json.loads((ROOT / "deploy" / "target" / "config" / "vm-166.json").read_text(encoding="utf-8"))
    assert committed == render.render_host(inv, "vm-166")            # the committed file is up to date


def test_policy_and_wiring_know_the_db_probe():
    from argus.infrastructure.wiring import EXECUTOR_KINDS
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert "db_probe" in EXECUTOR_KINDS
    assert pol["capabilities"]["database.health"] == {"max_per_incident": 3}
    assert pol["max_tool_level"] == 3


# --- the capability (argus/capabilities/catalog.py) ----------------------------------------------
def test_database_health_is_level_3_on_the_db_probe_executor():
    from argus.capabilities.catalog import build_catalog
    spec = next(s for s in build_catalog() if s.name == "database.health")
    assert spec.model_name == "inspect_database_health"
    assert (spec.level, spec.executor, spec.safety_class) == (3, "db_probe", "READ_ONLY_SAFE")
    assert "database" in spec.tags


def test_database_health_text_names_usage_clients_and_the_longest_transaction():
    from argus.capabilities.catalog import NoArgs, db_health
    from argus.domain.model import TargetInfo, TargetRef

    class Client:
        def get(self, path, params=None):
            assert (path, params) == ("/database/health", {"name": "argus-lab-db"})
            return {"database": "argus-lab-db", "ok": True, "max_connections": 20, "reserved_connections": 3,
                    "usable_connections": 17, "client_connections": 14, "usage_percent": 82.4,
                    "by_state": {"active": 2, "idle": 9, "idle in transaction": 3},
                    "by_client": [{"application_name": "shop-api", "role": "shop", "connections": 12}],
                    "longest_transactions": [{"pid": 4242, "application_name": "shop-api", "state": "idle in transaction",
                                              "wait_event_type": "Client", "wait_event": "ClientRead", "age_s": 912.5}],
                    "lock_waits": 1, "blocked_sessions": 1, "collected_at": "2026-10-07T16:00:00+00:00"}
    ref = TargetRef.parse(DB)
    r = db_health(NoArgs(), ref, TargetInfo(ref=ref, database="argus_lab"), Client())
    for part in ("14/17", "82.4%", "idle in transaction=3", "shop-api", "912.5 s", "lock waits=1"):
        assert part in r.model_text, part
    assert r.source_time is not None


def test_database_health_refuses_a_target_without_a_database():
    from argus.capabilities.catalog import NoArgs, db_health
    from argus.domain.model import TargetInfo, TargetRef
    ref = TargetRef.parse("vm-166/container:argus-lab-api")
    with pytest.raises(ExecutorError) as e:
        db_health(NoArgs(), ref, TargetInfo(ref=ref), None)
    assert e.value.category == "invalid_args"


def test_argus_reads_database_health_through_invoke_capability(make_app):
    app = make_app()
    inc = incident(app, DB)
    ctx = InvocationContext(incident=inc, caller="test", scope=app.runner.scope(inc.target))
    results = [app.runner.invoke(ctx, "inspect_database_health", {"target": DB})[0] for _ in range(4)]
    assert results[0].status == "ok", results[0]
    assert ("http://argus-v18-tunnel:18704", "/database/health") in FakeTargetAgent.calls
    assert [r.status for r in results] == ["ok", "ok", "ok", "refused"]       # max_per_incident: 3


# --- deployment -----------------------------------------------------------------------------------
def test_db_probe_service_runs_only_where_the_db_profile_is_enabled():
    tgt = yaml.safe_load((ROOT / "deploy" / "target" / "compose.target.yml").read_text(encoding="utf-8"))
    s = tgt["services"]["argus-v18-db-probe"]
    assert s["profiles"] == ["db"] and s["environment"]["ROLE"] == "db_probe"
    assert s["build"]["target"] == "db" and s["image"] == "argus-v18-target-db:1"
    assert set(s["networks"]) == {"argus-v18-mon", "argus-lab-app"} and "ports" not in s
    mounts = " ".join(s["volumes"])
    assert "docker.sock" not in mounts and "db_probe_token" in mounts and "db_monitor_password" in mounts
    loop = yaml.safe_load((ROOT / "deploy" / "target" / "compose.loopback.yml").read_text(encoding="utf-8"))
    assert loop["services"]["argus-v18-db-probe"]["ports"] == ["127.0.0.1:18704:8700"]
    env = lambda h: (ROOT / "deploy" / "target" / f"{h}.env").read_text(encoding="utf-8")   # noqa: E731
    assert "COMPOSE_PROFILES=db" in env("vm-166") and "COMPOSE_PROFILES" not in env("vm-095")


def test_db_probe_image_pins_its_driver_with_hashes():
    req = (ROOT / "services" / "target" / "requirements-db.txt").read_text(encoding="utf-8")
    pins = [ln for ln in req.splitlines() if ln and not ln.startswith("#")]
    names = {ln.split("==")[0] for ln in pins}
    assert {"pg8000", "scramp", "asn1crypto", "python-dateutil", "six"} <= names
    assert all("==" in ln and "--hash=sha256:" in ln for ln in pins)
    dockerfile = (ROOT / "services" / "target" / "Dockerfile").read_text(encoding="utf-8")
    assert "--require-hashes" in dockerfile and " AS db" in dockerfile


def test_lab_database_is_a_bounded_testing_only_baseline_container():
    lab = yaml.safe_load((ROOT / "deploy" / "lab" / "compose.lab.yml").read_text(encoding="utf-8"))
    s = lab["services"]["argus-lab-db"]
    assert s["image"] == "postgres:16-alpine" and s["profiles"] == ["base-166"]
    assert s["mem_limit"] and s["cpus"] and s["pids_limit"] and "ports" not in s
    assert any(t.startswith("/var/lib/postgresql/data") for t in s["tmpfs"])           # no Docker volume
    assert "max_connections=20" in " ".join(s["command"])
    assert s["healthcheck"]["test"][:2] == ["CMD", "pg_isready"]
    assert "POSTGRES_PASSWORD_FILE" in s["environment"]
    text = (ROOT / "deploy" / "lab" / "compose.lab.yml").read_text(encoding="utf-8")
    assert "testing only" in text.lower()
    init = (ROOT / "deploy" / "lab" / "db-init" / "10-argus-monitor.sh").read_text(encoding="utf-8")
    assert "GRANT pg_monitor TO argus_monitor" in init and "CONNECTION LIMIT" in init
    assert "\r\n" not in init
