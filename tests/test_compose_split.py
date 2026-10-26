"""T-0014 step 4: vm-095 runs three Argus programs from one image (ARCHITECTURE §3): api, worker, scheduler.

The api keeps the container name and the only host port; the worker and the scheduler publish none; the scheduler
gets the database credential and nothing else (no executor tokens, no model key); `serve` stays as the rollback.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CORE = yaml.safe_load((ROOT / "deploy" / "vm-095" / "compose.core.yml").read_text(encoding="utf-8"))["services"]


def test_three_programs_from_one_image():
    names = ("argus-v18-agent", "argus-v18-worker", "argus-v18-scheduler")
    assert all(n in CORE for n in names)
    assert {CORE[n]["image"] for n in names} == {"argus-v18-agent:1"}
    assert "build" in CORE["argus-v18-agent"] and "build" not in CORE["argus-v18-worker"]
    assert CORE["argus-v18-agent"]["command"][-1] == "${ARGUS_AGENT_CMD:-api}"     # rollback: ARGUS_AGENT_CMD=serve
    assert CORE["argus-v18-worker"]["command"][-1] == "worker"
    assert CORE["argus-v18-scheduler"]["command"][-1] == "scheduler"


def test_only_the_api_publishes_a_port_and_only_on_loopback():
    assert CORE["argus-v18-agent"]["ports"] == ["127.0.0.1:18000:8000"]
    assert "ports" not in CORE["argus-v18-worker"] and "ports" not in CORE["argus-v18-scheduler"]


def test_scheduler_gets_the_database_credential_and_the_digest_secrets_only():
    """No executor token and no model key; since phase 16 step 5 also the audit digest key and the OCI credential, from
    their own folder (tests/test_phase16_step5c_check.py checks that only the scheduler mounts them)."""
    vols = CORE["argus-v18-scheduler"]["volumes"]
    secrets = [v for v in vols if "/secrets/" in v]
    assert secrets == ["/opt/argus-v18/secrets/agent/db_password:/run/argus-secrets/db_password:ro",
                       "/opt/argus-v18/secrets/digest/audit_digest_ed25519_key:/run/argus-secrets/audit_digest_ed25519_key:ro",
                       "/opt/argus-v18/secrets/digest/oci_digest:/run/argus-secrets/oci_digest:ro"]
    assert all(v.endswith(":ro") for v in vols)
    env = CORE["argus-v18-scheduler"]["environment"]
    assert env["ARGUS_SCHEDULES"].startswith("/app/schedules/")                    # the image has no deploy/ folder
    assert any(v.startswith("/opt/argus-v18/app/deploy/scheduler:/app/schedules") for v in vols)
    assert "argus-v18-tunnel" not in CORE["argus-v18-scheduler"].get("depends_on", {})


def test_worker_has_its_lease_and_time_to_finish_a_run():
    w = CORE["argus-v18-worker"]
    assert w["environment"]["ARGUS_WORKER_LEASE_S"] and w["environment"]["ARGUS_SCHEDULE_MAX_QUEUED_AGE_S"]
    assert w["stop_grace_period"] == "120s"
    assert w["networks"] == ["argus-v18-core"]


AGENT_SECRETS = "/opt/argus-v18/secrets/agent"


def test_only_the_worker_mounts_the_executor_tokens():
    """T-0021 step 4 (§12.6): the tokens reach the worker container only, where the tools process reads them; the api
    gets its own files (database, JWT keys, model key for its status), never the token folders."""
    api = [v for v in CORE["argus-v18-agent"]["volumes"] if "/secrets/" in v]
    assert sorted(api) == [f"{AGENT_SECRETS}/{f}:/run/argus-secrets/{f}:ro"
                           for f in ("db_password", "jwt_ed25519_key", "jwt_signing_key", "openai_api_key")]
    assert f"{AGENT_SECRETS}:/run/argus-secrets:ro" in CORE["argus-v18-worker"]["volumes"]
    for name in ("argus-v18-agent", "argus-v18-scheduler"):
        assert not any(v.startswith(f"{AGENT_SECRETS}:") or "/vm-0" in v or "/vm-1" in v
                       for v in CORE[name]["volumes"])
