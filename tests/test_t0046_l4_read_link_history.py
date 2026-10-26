"""T-0046 step L4 (ACR-0025 §3.3-§3.5): the map, the incident charts and the investigation read the recorded link
transitions. The map gains `since` and `required` per link, and a broken required link is a critical problem of its
owner; the charts gain `link_broken` / `link_slow` / `link_recovered` events; `network.link_states` (Level 2,
in-worker, tag `link_states`) is registered and offered to no class."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from argus.adapters.outbound.config_adapters import YamlInventory
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.application.incident_metrics import IncidentMetrics, SignalList
from argus.application.topology import Topology
from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES
from argus.domain.model import Incident, RequestKind, TargetRef, TriggerKind
from argus.ports.ports import MetricsUnavailable, ProbeSample
from argus.tooling.executors import KnowledgeClient
from test_core import FakeMetrics, make_app  # noqa: F401  (make_app is a fixture)

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = """
hosts:
  h1: {executors: {prometheus: "http://prom-h1.internal:9090"}}
targets:
  - ref: h1/host:h1
  - ref: h1/container:web
    depends_on: [h1/container:db, {ref: h1/container:cache, required: false}]
  - ref: h1/container:db
    tcp_ports: [5432]
    depends_on: [h1/container:disk]
  - ref: h1/container:disk
    tcp_ports: [9000]
  - ref: h1/container:cache
    tcp_ports: [6379]
  - ref: h1/container:burner
    profile: scenario
    depends_on: [h1/container:db]
"""
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
WEB, DB, CACHE, DISK = (f"h1/container:{n}" for n in ("web", "db", "cache", "disk"))
S = {s.name: s for s in build_catalog()}["network.link_states"]


def sample(success, duration=0.01, kind=None):
    return ProbeSample(success, duration, NOW - timedelta(seconds=5), kind)


class Metrics(FakeMetrics):
    def __init__(self, probes=None, down=False):
        super().__init__({})
        self.probes, self.down = probes or {}, down

    def dependency_probes(self, target):
        if self.down:
            raise MetricsUnavailable("prometheus down")
        return self.probes.get(str(target), {})

    def dependency_probe_history(self, target, start, end):
        if self.down:
            raise MetricsUnavailable("prometheus down")
        return {name: [probe for probe in (sample if isinstance(sample, list) else [sample])
                       if start < probe.at <= end]
                for name, sample in self.probes.get(str(target), {}).items()}


@pytest.fixture()
def store(tmp_path):
    return SqliteStore(str(tmp_path / "l4.db"))


def topo(store, probes):
    return Topology(YamlInventory(INVENTORY), Metrics(probes), store, now=lambda: NOW)


def edge(body, a, b):
    return next(e for e in body["edges"] if e["from"] == a and e["to"] == b)


def node(body, ref):
    return next(n for n in body["nodes"] if n["id"] == ref)


# --- the map (§3.3) --------------------------------------------------------------------------------------------------
def test_each_link_says_whether_it_is_required(store):
    body = topo(store, {WEB: {"db": sample(1), "cache": sample(1)}}).view()
    assert edge(body, WEB, DB)["required"] is True             # a plain ref is required
    assert edge(body, WEB, CACHE)["required"] is False         # declared `required: false`


def test_since_is_the_last_recorded_transition_when_it_matches_the_state_now(store):
    store.add_link_event(WEB, DB, "ok", 3.0, None, NOW - timedelta(hours=2))
    store.add_link_event(WEB, DB, "broken", None, "connection refused", NOW - timedelta(minutes=7))
    store.add_link_event(WEB, CACHE, "broken", None, "timeout", NOW - timedelta(minutes=3))
    body = topo(store, {WEB: {"db": sample(0, kind="refused"), "cache": sample(1)}}).view()
    assert edge(body, WEB, DB)["since"] == "2026-10-21T11:53:00Z"
    assert edge(body, WEB, CACHE)["since"] is None             # the record says broken, the probe says ok now
    assert edge(body, DB, DISK)["since"] is None               # never recorded


def test_a_broken_required_link_is_a_critical_problem_of_its_owner(store):
    body = topo(store, {WEB: {"db": sample(0, kind="refused"), "cache": sample(1)}}).view()
    web = node(body, WEB)
    assert [p["kind"] for p in web["problems"]] == ["dependency_broken"]
    p = web["problems"][0]
    assert p["severity"] == "critical" and "db" in p["summary"] and "connection refused" in p["summary"]
    assert web["health"] == "failed"


def test_a_broken_optional_link_is_no_problem(store):
    body = topo(store, {WEB: {"db": sample(1), "cache": sample(0, kind="timeout")}}).view()
    assert edge(body, WEB, CACHE)["state"] == "broken"
    assert node(body, WEB)["problems"] == []


def test_an_idle_scenario_owner_stays_idle(store):
    body = topo(store, {"h1/container:burner": {"db": sample(0)}}).view()
    burner = node(body, "h1/container:burner")
    assert burner["idle"] is True and burner["problems"] == []


# --- the incident charts (§3.4) -------------------------------------------------------------------------------------
def charts(store, target=WEB, opened=NOW - timedelta(minutes=5)):
    inc = Incident(id="inc_l4charts", target=TargetRef.parse(target), trigger_kind=TriggerKind.manual,
                   request_kind=RequestKind.report, reason="r", principal="p", trigger_id="t", opened_at=opened)
    im = IncidentMetrics(FakeMetrics(), SignalList.from_data({"default": []}, set(), set()), now=lambda: NOW,
                         store=store, inventory=YamlInventory(INVENTORY))
    return [(e["kind"], e["label"]) for e in im.window(inc, "15m")["events"]]


def test_link_transitions_in_the_window_are_events(store):
    store.add_link_event(WEB, DB, "ok", 3.0, None, NOW - timedelta(hours=3))          # before the window: no event
    store.add_link_event(WEB, DB, "broken", None, "connection refused", NOW - timedelta(minutes=9))
    store.add_link_event(WEB, DB, "ok", 2.0, None, NOW - timedelta(minutes=4))
    store.add_link_event(WEB, CACHE, "slow", 230.0, None, NOW - timedelta(minutes=6))
    assert charts(store) == [("link_broken", "Link web → db broken (connection refused)"),
                             ("link_slow", "Link web → cache slow (230 ms)"),
                             ("link_recovered", "Link web → db recovered")]


def test_an_ok_after_nothing_or_unknown_and_an_unknown_are_no_events(store):
    store.add_link_event(WEB, DB, "ok", 3.0, None, NOW - timedelta(minutes=10))        # the recorder starting
    store.add_link_event(WEB, CACHE, "unknown", None, None, NOW - timedelta(minutes=8))
    store.add_link_event(WEB, CACHE, "ok", 1.0, None, NOW - timedelta(minutes=7))
    assert charts(store) == []


def test_the_previous_state_before_the_window_makes_a_recovery(store):
    store.add_link_event(WEB, DB, "broken", None, None, NOW - timedelta(hours=1))
    store.add_link_event(WEB, DB, "ok", 2.0, None, NOW - timedelta(minutes=2))
    assert charts(store) == [("link_recovered", "Link web → db recovered")]


def test_the_links_of_the_targets_dependencies_are_shown_once(store):
    store.add_link_event(DB, DISK, "broken", None, "timeout", NOW - timedelta(minutes=5))   # db's own link
    store.add_link_event(WEB, DB, "broken", None, None, NOW - timedelta(minutes=4))         # read for web and db
    assert charts(store) == [("link_broken", "Link db → disk broken (timeout)"),
                             ("link_broken", "Link web → db broken")]


# --- the investigation read (§3.5) ----------------------------------------------------------------------------------
def test_a_level_2_in_worker_read_offered_only_to_the_reviewed_classes():
    assert (S.model_name, S.level, S.safety_class, S.executor, S.runs_in) == (
        "read_link_states", 2, "READ_ONLY_SAFE", "argus_internal", "worker")
    assert set(S.target_kinds) == {"container"} and S.tags == frozenset({"link_states"})
    assert sorted(c.name for c in CLASSES if S.tags & c.tool_tags) == [
        "dependency_unavailable", "health_check_failed", "nginx_upstream_failure",
    ]
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert pol["capabilities"]["network.link_states"]["max_per_incident"] == 2


def client(store, probes=None, down=False):
    return KnowledgeClient(None, memory=store, inventory=YamlInventory(INVENTORY), metrics=Metrics(probes, down))


def read(store, target=WEB, minutes=30, **kw):
    inv = YamlInventory(INVENTORY)
    ref = TargetRef.parse(target)
    return S.impl(S.args_model(minutes=minutes), ref, inv.target(ref), client(store, **kw))


def test_the_read_gives_each_link_now_since_and_its_changes(store):
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    store.add_link_event(WEB, DB, "ok", 3.0, None, recent - timedelta(minutes=10))
    store.add_link_event(WEB, DB, "broken", None, "connection refused", recent)
    store.add_link_event(DB, DISK, "ok", 1.0, None, recent)
    r = read(store, probes={WEB: {"db": sample(0, kind="refused"), "cache": sample(1)}, DB: {"disk": sample(1)}})
    links = {(x["owner"], x["dependency"]): x for x in r.values["links"]}
    assert set(links) == {(WEB, DB), (WEB, CACHE), (DB, DISK)}
    db = links[(WEB, DB)]
    assert (db["state"], db["reason"], db["state_from"]) == ("broken", "connection refused", "probe")
    assert db["since"] is not None and [m["state"] for m in db["transitions"]] == ["ok", "broken"]
    assert "web -> db: broken (connection refused) since" in r.model_text
    assert r.status == "ok" and not r.partial


def test_an_unreadable_prometheus_gives_the_last_recorded_state_and_a_partial_answer(store):
    store.add_link_event(WEB, DB, "ok", 3.0, None, datetime.now(timezone.utc) - timedelta(minutes=3))
    r = read(store, down=True)
    links = {(x["owner"], x["dependency"]): x for x in r.values["links"]}
    assert (links[(WEB, DB)]["state"], links[(WEB, DB)]["state_from"]) == ("ok", "record")
    assert r.partial and r.values["unreadable_hosts"] == ["h1"] and "monitoring unreadable for h1" in r.model_text


def test_a_container_without_links_says_so(store):
    r = read(store, target=CACHE)
    assert r.values["links"] == [] and "none declared" in r.model_text


def test_the_minutes_are_bounded():
    with pytest.raises(ValueError):
        S.args_model(minutes=241)


def test_the_read_is_an_ordinary_observation_through_the_worker(make_app):
    app = make_app()
    target = TargetRef.parse("vm-166/container:argus-lab-api")
    app.store.add_link_event(str(target), "vm-166/container:argus-lab-cache", "broken", None, "timeout",
                             datetime.now(timezone.utc) - timedelta(minutes=2))
    obs = app.catalogue.call(S, S.args_model(minutes=30), target)
    assert obs.status == "ok" and obs.capability == "network.link_states" and obs.executor == "argus_internal"
    assert obs.values["links"][0]["transitions"][0]["state"] == "broken"
    client = app.catalogue.dispatcher.executors.client("argus_internal", "", None)
    assert client.inventory is not None and client.metrics is app.metrics
