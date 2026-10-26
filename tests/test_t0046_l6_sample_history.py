"""T-0046: retain every sampled link transition between scheduler ticks and across restarts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from argus.adapters.outbound.config_adapters import PrometheusMetrics, YamlInventory
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.application.link_transitions import LinkTransitions
from argus.domain.model import TargetRef
from argus.ports.ports import MetricsUnavailable, ProbeSample

INVENTORY = """
hosts:
  h1: {executors: {prometheus: "http://prom-h1.internal:9090"}}
targets:
  - ref: h1/host:h1
  - ref: h1/container:web
    depends_on: [h1/container:db]
  - ref: h1/container:db
    tcp_ports: [5432]
"""
OWNER = "h1/container:web"
DEPENDENCY = "h1/container:db"
T0 = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


class Metrics:
    def __init__(self, samples=()):
        self.samples = list(samples)
        self.down = False
        self.requests = []

    def dependency_probe_history(self, target, start, end):
        self.requests.append((str(target), start, end))
        if self.down:
            raise MetricsUnavailable("prometheus unavailable")
        return {"db": [sample for sample in self.samples if start < sample.at <= end]}

    def dependency_probes(self, target):
        if self.down:
            raise MetricsUnavailable("prometheus unavailable")
        return {"db": self.samples[-1]} if self.samples else {}


def probe(at, success, duration=0.01, error=None):
    return ProbeSample(success, duration, at, error)


@pytest.fixture()
def store(tmp_path):
    return SqliteStore(str(tmp_path / "link-history.db"))


def transition_rows(store):
    return store._q("SELECT state, at FROM link_event WHERE owner=? AND dependency=? ORDER BY at,id",
                    (OWNER, DEPENDENCY))


def test_records_every_sampled_transition_between_sixty_second_ticks(store):
    metrics = Metrics([
        probe(T0, 1),
        probe(T0 + timedelta(seconds=15), 0, error="refused"),
        probe(T0 + timedelta(seconds=30), 1),
    ])
    now = T0 + timedelta(seconds=60)

    result = LinkTransitions(store, inventory(), metrics, now=lambda: now).run_once()

    rows = transition_rows(store)
    assert [r[0] for r in rows] == ["ok", "broken", "ok"]
    assert [datetime.fromisoformat(r[1]) for r in rows] == [
        T0, T0 + timedelta(seconds=15), T0 + timedelta(seconds=30),
    ]
    assert result == "3 link change(s) recorded"
    assert [r["at"] for r in store.link_probe_cursors(OWNER).values()] == [T0 + timedelta(seconds=30)]


def test_cursor_survives_scheduler_restart_and_does_not_replay_samples(store):
    metrics = Metrics([probe(T0, 1), probe(T0 + timedelta(seconds=15), 0, error="timeout")])
    first = LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=20))
    first.run_once()
    before = transition_rows(store)

    restarted = LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=60))
    assert restarted.run_once() == "0 link change(s) recorded"
    assert transition_rows(store) == before
    assert metrics.requests[-1][1] == T0 + timedelta(seconds=15)


def test_prometheus_outage_does_not_advance_cursor_and_later_samples_are_replayed(store):
    metrics = Metrics([probe(T0, 1)])
    LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=10)).run_once()
    metrics.down = True
    assert "skipped (Prometheus unreadable): h1" in LinkTransitions(
        store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=60)).run_once()
    assert list(store.link_probe_cursors(OWNER).values())[0]["at"] == T0

    metrics.down = False
    metrics.samples.extend([
        probe(T0 + timedelta(seconds=15), 0, error="refused"),
        probe(T0 + timedelta(seconds=30), 1),
    ])
    assert LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=90)).run_once() == \
        "2 link change(s) recorded"
    assert [r[0] for r in transition_rows(store)] == ["ok", "broken", "ok"]


def test_replay_window_is_bounded_and_marks_the_omitted_gap_unknown(store):
    now = T0 + timedelta(hours=5)
    store.record_link_probe(OWNER, DEPENDENCY, "ok", 10, None, T0)
    metrics = Metrics([probe(now, 0, error="timeout")])

    LinkTransitions(store, inventory(), metrics, now=lambda: now).run_once()

    assert metrics.requests[-1][1] == now - timedelta(hours=4)
    assert [row[0] for row in transition_rows(store)] == ["ok", "unknown", "broken"]
    assert store.link_probe_cursors(OWNER)[DEPENDENCY]["at"] == now



def test_silence_after_the_last_sample_becomes_unknown_at_the_staleness_limit(store):
    metrics = Metrics([probe(T0, 1)])
    LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=10)).run_once()

    LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=100)).run_once()

    rows = transition_rows(store)
    assert [r[0] for r in rows] == ["ok", "unknown"]
    assert datetime.fromisoformat(rows[1][1]) == T0 + timedelta(seconds=90)


def test_a_gap_between_two_samples_longer_than_the_staleness_limit_is_unknown(store):
    metrics = Metrics([probe(T0, 1)])
    LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=10)).run_once()
    metrics.samples.append(probe(T0 + timedelta(seconds=100), 1))

    LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=110)).run_once()

    rows = transition_rows(store)
    assert [r[0] for r in rows] == ["ok", "unknown", "ok"]
    assert [datetime.fromisoformat(r[1]) for r in rows] == [
        T0, T0 + timedelta(seconds=90), T0 + timedelta(seconds=100),
    ]


def test_a_silent_exporter_keeps_each_window_short_and_records_unknown_once(store):
    metrics = Metrics([probe(T0, 1)])
    LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=10)).run_once()

    for tick in range(1, 11):                                   # ten minutes of 60 s ticks, no new sample
        LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=60 * tick)).run_once()

    assert [r[0] for r in transition_rows(store)] == ["ok", "unknown"]
    assert max(end - start for _, start, end in metrics.requests) <= timedelta(seconds=150)


def test_a_silent_exporter_keeps_each_window_short_across_long_scheduler_gaps(store):
    metrics = Metrics([probe(T0, 1)])
    LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(seconds=10)).run_once()

    for minutes in (2, 32, 62, 92, 122, 182):                   # the scheduler stops for 30 and 60 minutes
        LinkTransitions(store, inventory(), metrics, now=lambda: T0 + timedelta(minutes=minutes)).run_once()

    windows = [int((end - start).total_seconds()) for _, start, end in metrics.requests]
    assert windows == [90, 120, 90, 90, 90, 90, 90]             # the stale-detection read, then the staleness limit
    assert [r[0] for r in transition_rows(store)] == ["ok", "unknown"]


def test_sqlite_refuses_a_probe_older_than_the_cursor(store):
    assert store.record_link_probe(OWNER, DEPENDENCY, "ok", 10, None, T0) is True

    assert store.record_link_probe(OWNER, DEPENDENCY, "broken", None, "refused", T0 - timedelta(seconds=1)) is False
    assert store.record_link_probe(OWNER, DEPENDENCY, "broken", None, "refused", T0) is False

    assert [r[0] for r in transition_rows(store)] == ["ok"]
    assert store.link_probe_cursors(OWNER)[DEPENDENCY] == {"state": "ok", "at": T0}


def inventory():
    return YamlInventory(INVENTORY)


def test_prometheus_history_uses_source_sample_times_and_collapses_scrape_repeats(monkeypatch):
    evaluated = [T0 + timedelta(seconds=n) for n in (5, 10, 15, 20, 25, 30)]
    source = [stamp.timestamp() for stamp in
              (T0, T0, T0 + timedelta(seconds=15), T0 + timedelta(seconds=15),
               T0 + timedelta(seconds=30), T0 + timedelta(seconds=30))]
    success = [1, 1, 0, 0, 1, 1]
    calls = []

    class Response:
        def __init__(self, result):
            self.result = result

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"result": self.result}}

    def get(url, params, timeout):
        calls.append(params)
        query = params["query"]
        if "argus_probe_success" in query:
            values = source if query.startswith("timestamp(") else success
            kind = None
        elif "argus_probe_duration_seconds" in query:
            values = source if query.startswith("timestamp(") else [0.01, 0.01, 0.02, 0.02, 0.01, 0.01]
            kind = None
        else:
            selected_times = [2, 3]
            values = ([source[index] for index in selected_times] if query.startswith("timestamp(")
                      else [1, 1])
            result = [{"metric": {"dependency": "db", "kind": "refused"}, "values": [
                [evaluated[index].timestamp(), str(value)]
                for index, value in zip(selected_times, values)
            ]}]
            return Response(result)
        kind = None
        labels = {"dependency": "db"}
        if kind:
            labels["kind"] = kind
        result = [{"metric": labels, "values": [
            [stamp.timestamp(), str(value)] for stamp, value in zip(evaluated, values)
        ]}]
        return Response(result)

    monkeypatch.setattr("argus.adapters.outbound.config_adapters.httpx.get", get)
    metrics = PrometheusMetrics(inventory(), {
        "dependency_probe_success": 'argus_probe_success{owner="$name"}',
        "dependency_probe_duration_s": 'argus_probe_duration_seconds{owner="$name"}',
        "dependency_probe_error": 'argus_probe_error{owner="$name"}',
    })

    history = metrics.dependency_probe_history(TargetRef.parse(OWNER), T0 - timedelta(seconds=1),
                                              T0 + timedelta(seconds=35))

    samples = history["db"]
    assert [(sample.success, sample.error_kind, sample.at) for sample in samples] == [
        (1.0, None, T0), (0.0, "refused", T0 + timedelta(seconds=15)),
        (1.0, None, T0 + timedelta(seconds=30)),
    ]
    assert len(calls) == 6
    assert all(call["step"] == "5s" for call in calls)
    assert sum(call["query"].startswith("timestamp(") for call in calls) == 3
