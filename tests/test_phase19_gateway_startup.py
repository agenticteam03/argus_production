"""The service image cannot start with a wildcard or own-host action route."""
from __future__ import annotations

import json

import pytest

from services.action_gateway.run import load_config


def test_gateway_config_starts_closed_and_rejects_unreviewed_pairs(tmp_path):
    path = tmp_path / "action-gateway.json"
    path.write_text(json.dumps({"host": "vm-166", "released": []}), encoding="utf-8")
    host, pairs = load_config(path)
    assert host == "vm-166" and pairs == {}
    path.write_text(json.dumps({"host": "vm-095", "released": [{
        "capability": "container.start", "target": "vm-095/container:argus-lab-cache",
        "route": "POST /containers/argus-lab-cache/start",
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="own host"):
        load_config(path)
    path.write_text(json.dumps({"host": "vm-166", "released": [{
        "capability": "container.start", "target": "vm-166/container:argus-lab-cache",
        "route": "POST /containers/argus-lab-cache/start", "extra": "unreviewed",
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="fields"):
        load_config(path)


def test_closed_example_cannot_start_a_service_or_mount_a_token(monkeypatch):
    from pathlib import Path
    import services.action_gateway.run as run

    root = Path(__file__).resolve().parents[1]
    config = root / "deploy" / "action_gateway" / "closed.example.json"
    monkeypatch.setattr(run, "CONFIG", config)
    with pytest.raises(RuntimeError, match="empty release map"):
        run.main()
    # Phase 20 (X-3): only compose.actions.yml defines the services, and nothing loads it
    # (tests/test_phase20_action_services.py); every other compose file defines no gateway service and mounts no token.
    # X-5: vm-095 names the gateway only as the tunnel's alias and in the worker's URL (checked in that file too).
    compose = "\n".join(path.read_text(encoding="utf-8") for path in (root / "deploy").rglob("compose*.yml")
                        if path.name != "compose.actions.yml")
    named = sorted(line.strip() for line in compose.splitlines() if "argus-v18-action-gateway" in line)
    assert named == ["ARGUS_ACTION_GATEWAY_URL: http://argus-v18-action-gateway:18705",
                     "aliases: [argus-v18-action-gateway]"]
    assert "action_token" not in compose.replace("ARGUS_ACTION_TOKEN_FILE: /run/argus-secrets/action_token", "")
