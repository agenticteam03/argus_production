"""The model sees which URLs and ports each target allows, and is not offered a probe on a target that allows none.

EVAL-3 step 2 and T-0019 batch 3c: `check_http_endpoint` was called 11 times on `argus-lab-slow`, which has no HTTP
endpoint in the inventory (only TCP 8080); every call failed as `invalid_args`, and the three nginx misses escalated or
named no root cause after it ("the direct probe was invalid"). The tool definitions now carry, per target, the values
the inventory allows (`http_endpoints` for `url`, `tcp_ports` for `port`): the target enum keeps only the targets with
some, the argument gets an enum, and the description lists them. A probe with no allowed target is not offered.
"""
from __future__ import annotations

from argus.capabilities.catalog import build_catalog
from argus.domain.model import TargetRef
from argus.orchestration.view import InvestigationView
from argus.tooling.model_harness import ModelHarness

SPECS = {s.name: s for s in build_catalog()}
NGINX, SLOW = TargetRef.parse("vm-166/container:argus-lab-nginx"), TargetRef.parse("vm-166/container:argus-lab-slow")
URL = "http://argus-lab-nginx:8080/"


def _view(scope, allowed, names=("network.http_probe", "network.tcp_connect", "container.status")):
    return InvestigationView(incident=None, incident_class=None, findings=[], passages=[], evidence=[],
                             decisions_so_far=[], offered_specs=[SPECS[n] for n in names], scope=scope,
                             steps_left=5, max_reads_per_step=2, allowed_values=allowed)


def _tools(view):
    return {t.name: t for t in ModelHarness(llm=None).tool_definitions(view)}


def test_a_probe_is_offered_only_on_targets_with_allowed_values():
    tools = _tools(_view([NGINX, SLOW], {str(NGINX): {"url": [URL]}, str(SLOW): {"port": [8080]}}))
    http, tcp = tools["check_http_endpoint"], tools["check_tcp_connection"]
    assert http.parameters_schema["properties"]["target"]["enum"] == [str(NGINX)]
    assert http.parameters_schema["properties"]["url"]["enum"] == [URL]
    assert f"{NGINX}: {URL}" in http.description
    assert tcp.parameters_schema["properties"]["target"]["enum"] == [str(SLOW)]
    assert tcp.parameters_schema["properties"]["port"]["enum"] == [8080]
    assert f"{SLOW}: 8080" in tcp.description
    # a tool without such an argument is unchanged
    assert tools["get_container_status"].parameters_schema["properties"]["target"]["enum"] == [str(NGINX), str(SLOW)]


def test_a_probe_with_no_allowed_target_is_not_offered():
    tools = _tools(_view([SLOW], {str(SLOW): {"port": [8080]}}))
    assert "check_http_endpoint" not in tools and "check_tcp_connection" in tools


def test_the_runner_fills_the_allowed_values_from_the_inventory():
    from pathlib import Path

    from argus.adapters.outbound.config_adapters import YamlInventory
    from argus.orchestration.runner import allowed_values

    inv = YamlInventory((Path(__file__).resolve().parents[1] / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    got = allowed_values(inv, [NGINX, SLOW, TargetRef.parse("vm-166/host:vm-166")])
    assert got[str(NGINX)]["url"] == [URL] and got[str(SLOW)]["port"] == [8080]
    assert got[str(SLOW)]["url"] == [] and got["vm-166/host:vm-166"] == {"url": [], "port": []}
