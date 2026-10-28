"""Phase 20: the first lab release candidate must agree with the inventory, the action card, the risk table and both
gateway ACL layers, and stay inert until a separately reviewed release PR opens the write gate."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from services.action_gateway.run import load_config
from services.action_gateway.socket_proxy import ProxyRefused, SocketProxyPolicy

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "deploy/action_gateway/first-lab-release.candidate.json"
TARGET = "vm-166/container:argus-lab-cache"
WORKER = "vm-166/container:argus-lab-jobworker"
PAIR = ("container.start", TARGET)
WORKER_PAIR = ("container.restart", WORKER)
ROUTE = "POST /containers/argus-lab-cache/start"
WORKER_ROUTE = "POST /containers/argus-lab-jobworker/restart"
ACTION_ID = "act_" + "a" * 32


def _yaml(relative):
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def test_the_candidate_is_exactly_the_two_reviewed_pairs():
    host, pairs = load_config(CANDIDATE)
    assert host == "vm-166"
    assert pairs == {PAIR: ROUTE, WORKER_PAIR: WORKER_ROUTE}

    service = next(row["service"] for row in _yaml("config/inventory.yaml")["targets"] if row["ref"] == TARGET)
    card = _yaml("config/actions/container.start.yaml")
    assert PAIR[0] in service["safe_actions"] and PAIR[0] not in service.get("never", [])
    assert "POST " + card["route"].format(name="argus-lab-cache") == ROUTE
    assert _yaml("config/risk.yaml")["matrix"][PAIR[0]][service["kind"]] == "green"

    worker = next(row["service"] for row in _yaml("config/inventory.yaml")["targets"] if row["ref"] == WORKER)
    restart = _yaml("config/actions/container.restart.yaml")
    assert WORKER_PAIR[0] in worker["safe_actions"] and WORKER_PAIR[0] not in worker.get("never", [])
    assert "POST " + restart["route"].format(name="argus-lab-jobworker") == WORKER_ROUTE
    assert _yaml("config/risk.yaml")["matrix"][WORKER_PAIR[0]][worker["kind"]] == "green"


def test_only_the_candidate_pairs_are_released():
    assert _yaml("config/policy.yaml")["write_gate"]["open"] == [
        {"capability": "container.start", "target": TARGET},
        {"capability": "container.restart", "target": WORKER},
    ]
    for compose in ROOT.glob("deploy/**/compose*.yml"):
        assert CANDIDATE.name not in compose.read_text(encoding="utf-8"), compose


def test_the_candidate_proxy_grants_one_inspect_and_one_write_path_per_pair():
    _, pairs = load_config(CANDIDATE)
    seen = []

    def docker(method, path, action_id):
        seen.append((method, path, action_id))
        return (200, b'{"Id":"cache-id"}') if method == "GET" else (204, b"")

    proxy = SocketProxyPolicy("vm-166", pairs, docker)
    assert proxy.forward("GET", "/containers/argus-lab-cache/json") == (200, b'{"Id":"cache-id"}')
    assert proxy.forward("POST", "/containers/argus-lab-cache/start", action_id=ACTION_ID) == (204, b"")
    assert proxy.forward("GET", "/containers/argus-lab-jobworker/json") == (200, b'{"Id":"cache-id"}')
    assert proxy.forward("POST", "/containers/argus-lab-jobworker/restart", action_id=ACTION_ID) == (204, b"")
    for method, path in (("POST", "/containers/argus-lab-cache/restart"),
                         ("POST", "/containers/argus-lab-jobworker/start"),
                         ("POST", "/containers/argus-lab-jobworker/stop"),
                         ("POST", "/containers/argus-lab-api/start"),
                         ("POST", "/containers/argus-lab-api/restart"),
                         ("GET", "/containers/argus-lab-api/json")):
        with pytest.raises(ProxyRefused):
            proxy.forward(method, path, action_id=ACTION_ID if method == "POST" else None)
    assert seen == [("GET", "/containers/argus-lab-cache/json", None),
                    ("POST", "/containers/argus-lab-cache/start", ACTION_ID),
                    ("GET", "/containers/argus-lab-jobworker/json", None),
                    ("POST", "/containers/argus-lab-jobworker/restart", ACTION_ID)]
