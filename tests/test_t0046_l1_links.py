"""T-0046 step L1 (ACR-0025): the link-state rules in one place (`application/links.py`, shared by the topology and the
scheduler's recording in L3), and an inventory `depends_on` entry that may say `{ref, port, required}`."""
from __future__ import annotations

import importlib.util
import json
from datetime import timedelta

import pytest
import yaml

from argus.adapters.outbound.config_adapters import YamlInventory
from argus.application.links import LINK_WARNING_MS, link_state
from argus.application.topology import Topology
from argus.domain.model import TargetRef
from argus.ports.ports import ProbeSample
from test_core import ROOT
from test_t0045_b3_topology import NOW, Metrics, NoStore, edge


def sample(success, duration=0.01, kind=None):
    return ProbeSample(success, duration, NOW - timedelta(seconds=5), kind)


# --- the rules ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("probe, port, want", [
    (None, 6379, ("unknown", None, None)),                                  # no sample
    (ProbeSample(None, None, NOW), 6379, ("unknown", None, None)),           # stale: never ok
    (sample(1), None, ("unknown", 10.0, None)),                              # no port: a host dependency, not probed
    (sample(1, 0.01), 6379, ("ok", 10.0, None)),
    (sample(1, 0.25), 6379, ("slow", 250.0, None)),                          # above the default 100 ms
    (sample(0, 0.002, "refused"), 6379, ("broken", 2.0, "connection refused")),
    (sample(0, None, "timeout"), 6379, ("broken", None, "timeout")),
    (sample(0, None, "other"), 6379, ("broken", None, None)),                # the topology says "not reachable"
])
def test_the_state_of_one_link(probe, port, want):
    assert link_state(probe, port) == want


def test_an_owner_may_set_its_own_slow_limit():
    assert LINK_WARNING_MS == 100.0
    assert link_state(sample(1, 0.25), 6379, warn_ms=400)[0] == "ok"


# --- the inventory mapping ---------------------------------------------------------------------------------------------
def inventory(web_depends: str, extra: str = "") -> str:
    return f"""
hosts:
  h1: {{executors: {{}}}}
  h2: {{executors: {{}}}}
targets:
  - ref: h1/host:h1
  - ref: h2/container:far
    tcp_ports: [80]
  - ref: h1/container:web
    depends_on: {web_depends}
  - ref: h1/container:db
    tcp_ports: [5432, 5433]
  - ref: h1/container:cache
    tcp_ports: [6379]
{extra}"""


def test_a_plain_ref_and_a_mapping_load_the_same_link():
    plain = YamlInventory(inventory("[h1/container:cache]")).target(TargetRef.parse("h1/container:web"))
    mapped = YamlInventory(inventory("[{ref: h1/container:cache, port: 6379, required: true}]")).target(
        TargetRef.parse("h1/container:web"))
    cache = TargetRef.parse("h1/container:cache")
    assert plain.depends_on == mapped.depends_on == [cache]
    assert plain.link_port(cache, [6379]) == mapped.link_port(cache, [6379]) == 6379
    assert plain.link(cache).required and mapped.link(cache).required


def test_a_mapping_names_its_port_and_may_be_not_required():
    web = YamlInventory(inventory("[{ref: h1/container:db, port: 5433, required: false}, h1/host:h1]")).target(
        TargetRef.parse("h1/container:web"))
    db, host = TargetRef.parse("h1/container:db"), TargetRef.parse("h1/host:h1")
    assert web.depends_on == [db, host]
    assert web.link_port(db, [5432, 5433]) == 5433 and web.link(db).required is False
    assert web.link_port(host, []) is None and web.link(host).required is True        # a host dependency: no port


@pytest.mark.parametrize("entry, words", [
    ("[{ref: h1/container:db, port: 6000}]", "does not list"),               # a port the dependency does not list
    ("[{ref: h1/host:h1, port: 22}]", "host dependency has no port"),        # a port on a host-kind ref
    ("[h2/container:far]", "another host"),                                  # cross-host: links are per host
    ("[{ref: h2/container:far, port: 80}]", "another host"),
    ("[{ref: h1/container:db, port: '5432'}]", "TCP port number"),
    ("[{ref: h1/container:db, port: true}]", "TCP port number"),
    ("[{ref: h1/container:db, required: 'yes'}]", "true or false"),
    ("[{ref: h1/container:db, prot: 5432}]", "a ref or {ref, port, required}"),   # a misspelt key is refused
    ("[{port: 5432}]", "a ref or {ref, port, required}"),
])
def test_the_loader_refuses(entry, words):
    with pytest.raises(ValueError, match=words.replace("{", r"\{").replace("}", r"\}")):
        YamlInventory(inventory(entry))


def test_the_deployed_inventory_still_loads():
    YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))


# --- the map: a mapping and a plain ref give the same edge -------------------------------------------------------------
def topo(text):
    return Topology(YamlInventory(text), Metrics({}, {"h1/container:web": {"cache": sample(0, 0.002, "refused"),
                                                                            "db": sample(1, 0.02)}}),
                    NoStore(), now=lambda: NOW)


def test_a_mapping_and_a_plain_ref_give_the_same_edge():
    plain = edge(topo(inventory("[h1/container:cache]")).view(), "web", "cache")
    mapped = edge(topo(inventory("[{ref: h1/container:cache, port: 6379}]")).view(), "web", "cache")
    assert plain == mapped
    assert plain["state"] == "broken" and plain["reason"] == "connection refused" and plain["port"] == 6379


def test_the_edge_uses_the_declared_port():
    plain = edge(topo(inventory("[h1/container:db]")).view(), "web", "db")
    mapped = edge(topo(inventory("[{ref: h1/container:db, port: 5433}]")).view(), "web", "db")
    assert plain["port"] == 5432 and plain["id"].endswith(":5432")          # unchanged: the first listed port
    assert mapped["port"] == 5433 and mapped["id"].endswith(":5433") and mapped["label"] == "tcp 5433"


# --- the exporter's probe list follows the same entry ------------------------------------------------------------------
def _render():
    spec = importlib.util.spec_from_file_location("render_t0046", ROOT / "ops" / "render_target_config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_declared_port_is_the_only_one_probed():
    render = _render()
    plain = render.render_host(yaml.safe_load(inventory("[h1/container:db]")), "h1")["probes"]
    mapped = render.render_host(yaml.safe_load(inventory("[{ref: h1/container:db, port: 5433}]")), "h1")["probes"]
    assert [p["port"] for p in plain] == [5432, 5433]                       # unchanged: every listed port
    assert mapped == [{"owner": "web", "dependency": "db", "host": "db", "port": 5433}]


def test_the_rendered_target_config_is_unchanged_for_the_deployed_inventory():
    render = _render()
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    for host in inv["hosts"]:
        committed = json.loads((ROOT / "deploy" / "target" / "config" / f"{host}.json").read_text(encoding="utf-8"))
        assert render.render_host(inv, host) == committed
