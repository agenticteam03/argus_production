"""The first lab release candidate must agree across inventory, cards and gateway ACL."""
from __future__ import annotations

from pathlib import Path

import yaml

from services.action_gateway.run import load_config
from services.action_gateway.socket_proxy import ProxyRefused, SocketProxyPolicy


ROOT = Path(__file__).resolve().parents[1]
TARGET = "vm-166/container:argus-lab-cache"
PAIR = ("container.start", TARGET)
ROUTE = "POST /containers/argus-lab-cache/start"


def test_first_release_candidate_is_the_single_reviewed_pair():
    host, pairs = load_config(ROOT / "deploy/action_gateway/first-lab-release.candidate.json")
    assert host == "vm-166"
    assert pairs == {PAIR: ROUTE}

    inventory = yaml.safe_load((ROOT / "config/inventory.yaml").read_text(encoding="utf-8"))
    service = next(row["service"] for row in inventory["targets"] if row["ref"] == TARGET)
    card = yaml.safe_load((ROOT / "config/actions/container.start.yaml").read_text(encoding="utf-8"))
    risk = yaml.safe_load((ROOT / "config/risk.yaml").read_text(encoding="utf-8"))
    assert PAIR[0] in service["safe_actions"] and PAIR[0] not in service.get("never", [])
    assert card["route"].format(name="argus-lab-cache") == ROUTE.removeprefix("POST ")
    assert risk["matrix"][PAIR[0]][service["kind"]] == "green"

    # The candidate is inert until a later, separately reviewed activation.
    policy = yaml.safe_load((ROOT / "config/policy.yaml").read_text(encoding="utf-8"))
    assert policy["write_gate"]["open"] == []


def test_candidate_proxy_grants_one_inspect_and_one_write_path():
    _, pairs = load_config(ROOT / "deploy/action_gateway/first-lab-release.candidate.json")
    seen = []

    def docker(method, path, action_id):
        seen.append((method, path, action_id))
        return (200, b'{"Id":"cache-id"}') if method == "GET" else (204, b"")

    proxy = SocketProxyPolicy("vm-166", pairs, docker)
    assert proxy.forward("GET", "/containers/argus-lab-cache/json") == (200, b'{"Id":"cache-id"}')
    action_id = "act_" + "a" * 32
    assert proxy.forward("POST", "/containers/argus-lab-cache/start", action_id=action_id) == (204, b"")
    for method, path in (("POST", "/containers/argus-lab-cache/restart"),
                         ("POST", "/containers/argus-lab-worker/start"),
                         ("GET", "/containers/argus-lab-worker/json")):
        try:
            proxy.forward(method, path, action_id=action_id if method == "POST" else None)
        except ProxyRefused:
            pass
        else:
            raise AssertionError(f"unreleased Docker route passed: {method} {path}")
    assert seen == [("GET", "/containers/argus-lab-cache/json", None),
                    ("POST", "/containers/argus-lab-cache/start", action_id)]
