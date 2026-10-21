"""T-0046 step L3 (ACR-0025 §3.1): the scheduler records each declared container link's state when it changes, from the
owner's own host's probes, with the topology's rules; a host whose Prometheus cannot be read is skipped for the tick."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from argus.adapters.outbound.config_adapters import YamlInventory
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.application.link_transitions import LinkTransitions
from argus.infrastructure.scheduler import Scheduler, load_reconcile
from argus.ports.ports import MetricsUnavailable, ProbeSample, StaleMetrics
from test_core import ROOT

INVENTORY = """
hosts:
  h1: {executors: {prometheus: "http://prom-h1.internal:9090"}}
  h2: {executors: {prometheus: "http://prom-h2.internal:9090"}}
targets:
  - ref: h1/host:h1
  - ref: h1/container:web
    depends_on: [h1/container:db, h1/container:cache]
  - ref: h1/container:db
    tcp_ports: [5432]
  - ref: h1/container:cache
    tcp_ports: [6379]
  - ref: h1/container:filler
    depends_on: [h1/host:h1]
  - ref: h2/host:h2
  - ref: h2/container:api
    depends_on: [h2/container:queue]
    link_warning_ms: 400
  - ref: h2/container:queue
    tcp_ports: [5672]
"""
T0 = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
WEB_DB, WEB_CACHE, API_QUEUE = ("h1/container:web", "h1/container:db"), ("h1/container:web", "h1/container:cache"), \
    ("h2/container:api", "h2/container:queue")


def sample(success, duration=0.01, kind=None):
    return ProbeSample(success, duration, T0, kind)


class Metrics:
    """Probes per owner; a host in `down` raises MetricsUnavailable, one in `stale` StaleMetrics. Records each read."""

    def __init__(self, probes):
        self.probes, self.down, self.stale, self.reads = probes, set(), set(), []

    def dependency_probes(self, target):
        self.reads.append(str(target))
        if target.host in self.down:
            raise MetricsUnavailable(f"prometheus for {target.host}")
        if target.host in self.stale:
            raise StaleMetrics("no fresh samples")
        return self.probes.get(str(target), {})


class Store(SqliteStore):
    def __init__(self, path):
        super().__init__(path)
        self.audits = []

    def append(self, record):
        super().append(record)
        self.audits.append(record)


@pytest.fixture()
def store(tmp_path):
    return Store(str(tmp_path / "l3.db"))


def healthy():
    return {"h1/container:web": {"db": sample(1), "cache": sample(1)}, "h2/container:api": {"queue": sample(1)}}


def recorder(store, metrics):
    clock = {"now": T0}
    rec = LinkTransitions(store, YamlInventory(INVENTORY), metrics, now=lambda: clock["now"])
    return rec, clock


def rows(store, owner="h1/container:web"):
    """What the recorder wrote, every row (the stores' reads skip a row that repeats its link's state, L4)."""
    return [tuple(r) for r in store._q("SELECT owner, dependency, state FROM link_event WHERE owner=? ORDER BY at, id",
                                       (owner,))]


def test_the_first_tick_records_every_link_once(store):
    rec, _ = recorder(store, Metrics(healthy()))
    rec.run_once()
    assert sorted(rows(store)) == sorted([(*WEB_DB, "ok"), (*WEB_CACHE, "ok")])
    assert rows(store, "h2/container:api") == [(*API_QUEUE, "ok")]
    assert {(a.event, a.detail["from"]) for a in store.audits} == {("link.changed", None)}


def test_no_row_while_nothing_changes(store):
    rec, clock = recorder(store, Metrics(healthy()))
    rec.run_once()
    before = len(rows(store)) + len(rows(store, "h2/container:api"))
    for i in range(5):
        clock["now"] = T0 + timedelta(minutes=i + 1)
        assert rec.run_once().startswith("0 link change(s)")
    assert len(rows(store)) + len(rows(store, "h2/container:api")) == before


def test_one_row_per_change_audited_with_both_states(store):
    m = Metrics(healthy())
    rec, clock = recorder(store, m)
    rec.run_once()
    m.probes["h1/container:web"]["db"] = sample(0, kind="refused")
    clock["now"] = T0 + timedelta(minutes=1)
    rec.run_once()
    m.probes["h1/container:web"]["db"] = sample(1, duration=0.2)       # 200 ms > 100 ms: slow
    clock["now"] = T0 + timedelta(minutes=2)
    rec.run_once()
    db = [r for r in store.link_events("h1/container:db", T0 - timedelta(1), T0 + timedelta(1))]
    assert [(r["state"], r["reason"]) for r in db] == [("ok", None), ("broken", "connection refused"), ("slow", None)]
    changed = [a.detail for a in store.audits if a.detail["dependency"] == "h1/container:db"]
    assert [(d["from"], d["to"]) for d in changed] == [(None, "ok"), ("ok", "broken"), ("broken", "slow")]
    assert all(a.actor == "scheduler" for a in store.audits)


def test_the_owners_link_warning_is_used(store):
    m = Metrics(healthy())
    m.probes["h2/container:api"]["queue"] = sample(1, duration=0.3)    # 300 ms: under api's 400 ms
    rec, _ = recorder(store, m)
    rec.run_once()
    assert rows(store, "h2/container:api") == [(*API_QUEUE, "ok")]


def test_a_missing_or_stale_sample_is_unknown(store):
    m = Metrics(healthy())
    del m.probes["h1/container:web"]["cache"]                          # missing
    m.stale.add("h2")                                                  # read, but nothing fresh
    rec, _ = recorder(store, m)
    rec.run_once()
    assert (*WEB_CACHE, "unknown") in rows(store)
    assert rows(store, "h2/container:api") == [(*API_QUEUE, "unknown")]


def test_each_owner_is_read_on_its_own_host_only(store):
    m = Metrics(healthy())
    rec, _ = recorder(store, m)
    rec.run_once()
    assert sorted(m.reads) == ["h1/container:web", "h2/container:api"]


def test_a_prometheus_failure_skips_that_host_for_the_tick_only(store):
    m = Metrics(healthy())
    rec, clock = recorder(store, m)
    rec.run_once()
    m.down.add("h1")
    m.probes["h2/container:api"]["queue"] = sample(0, kind="timeout")
    clock["now"] = T0 + timedelta(minutes=1)
    summary = rec.run_once()
    assert "skipped (Prometheus unreadable): h1" in summary
    assert [r[2] for r in rows(store) if r[1] == "h1/container:db"] == ["ok"]           # no `unknown` burst
    assert [r[2] for r in rows(store, "h2/container:api")] == ["ok", "broken"]          # the other host goes on
    m.down.clear()
    clock["now"] = T0 + timedelta(minutes=2)
    rec.run_once()
    assert [r[2] for r in rows(store) if r[1] == "h1/container:db"] == ["ok"]           # and no recovery burst


def test_a_host_dependency_is_never_probed_or_recorded(store):
    m = Metrics(healthy())
    rec, _ = recorder(store, m)
    assert "h1/container:filler" not in [str(t.ref) for t in rec.owners()]
    rec.run_once()
    assert "h1/container:filler" not in m.reads
    assert rows(store, "h1/container:filler") == []


def test_a_restarted_scheduler_records_the_current_state_once(store):
    rec, _ = recorder(store, Metrics(healthy()))
    rec.run_once()
    again, _ = recorder(store, Metrics(healthy()))
    again.run_once()
    assert [r[2] for r in rows(store) if r[1] == "h1/container:db"] == ["ok", "ok"]     # "once at startup"


# --- configuration and the scheduler loop ---------------------------------------------------------------------------
def test_link_states_is_off_unless_enabled():
    assert load_reconcile("reconcile_firing_alerts: {enabled: true}").link_states is False
    on = load_reconcile("reconcile_firing_alerts: {enabled: true, link_states: {enabled: true}}")
    assert on.link_states is True and on.enabled is True


@pytest.mark.parametrize("text, error", [
    ("reconcile_firing_alerts: {enabled: true, link_states: {enabled: true, every_s: 5}}", "unknown field"),
    ("reconcile_firing_alerts: {enabled: false, link_states: {enabled: true}}", "reconcile tick"),
])
def test_a_bad_link_states_setting_is_refused(text, error):
    with pytest.raises(ValueError, match=error):
        load_reconcile(text)


def test_the_shipped_file_has_link_states_on_with_the_reconcile():
    """T-0046 L5 turned it on (vm-095, migration 009 applied); it runs on the reconcile tick, so that is on too."""
    text = (ROOT / "deploy" / "scheduler" / "schedules.yaml").read_text(encoding="utf-8")
    cfg = load_reconcile(text)
    assert cfg.link_states is True and cfg.enabled is True


def test_a_link_failure_never_stops_the_alert_reconciliation(store):
    stop, calls = threading.Event(), []

    class Reconcile:
        def run_once(self):
            calls.append("reconcile")
            return "ok"

    class Broken:
        def run_once(self):
            calls.append("links")
            stop.set()
            raise RuntimeError("prometheus answered nonsense")

    Scheduler(store, [], Reconcile(), 60, links=Broken()).run_forever(stop, every_s=0)
    assert calls == ["reconcile", "links"]
