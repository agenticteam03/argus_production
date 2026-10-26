"""T-0046: a durable sample cursor prevents replaying already processed probes after a scheduler restart."""
from __future__ import annotations

from datetime import timedelta

from argus.adapters.outbound.config_adapters import YamlInventory
from argus.application.link_transitions import LinkTransitions
from test_t0046_l4_read_link_history import (DB, INVENTORY, NOW, WEB, Metrics, charts, edge, sample,  # noqa: F401
                                            store, topo)

CACHE = "h1/container:cache"


def restart(store, probes, at):
    """A new scheduler process resumes from the persisted per-link source-sample cursor."""
    aligned = {}
    for owner, values in probes.items():
        cursors = store.link_probe_cursors(owner)
        aligned[owner] = {}
        for dep, value in values.items():
            cursor_data = cursors.get(f"h1/container:{dep}", {})
            cursor = cursor_data.get("at", at - timedelta(seconds=90))
            samples = []
            sample_at = cursor + timedelta(seconds=15)
            while sample_at < at:
                previous_state = cursor_data.get("state", "ok")
                previous_sample = value._replace(success=0 if previous_state == "broken" else 1,
                                                  error_kind="refused" if previous_state == "broken" else None,
                                                  at=sample_at)
                samples.append(previous_sample)
                sample_at += timedelta(seconds=15)
            samples.append(value._replace(at=at))
            aligned[owner][dep] = samples
    LinkTransitions(store, YamlInventory(INVENTORY), Metrics(aligned), now=lambda: at).run_once()


def test_a_restart_repeats_rows_but_not_transitions(store):
    broken = {WEB: {"db": sample(0, kind="refused"), "cache": sample(1)}}
    restart(store, {WEB: {"db": sample(1), "cache": sample(1)}}, NOW - timedelta(minutes=12))
    restart(store, broken, NOW - timedelta(minutes=8))            # the link breaks: one transition
    restart(store, broken, NOW - timedelta(minutes=3))            # a deploy while it is still broken
    rows = store.link_events(WEB, NOW - timedelta(hours=1), NOW)
    assert [(r["dependency"], r["state"]) for r in rows if r["dependency"] == DB] == [(DB, "ok"), (DB, "broken")]
    assert store.latest_link_events()[(WEB, DB)]["at"] == NOW - timedelta(minutes=8)


def test_the_map_keeps_the_real_since_across_a_restart(store):
    store.add_link_event(WEB, DB, "broken", None, "connection refused", NOW - timedelta(minutes=7))
    store.add_link_event(WEB, DB, "broken", None, "connection refused", NOW - timedelta(minutes=2))
    body = topo(store, {WEB: {"db": sample(0, kind="refused"), "cache": sample(1)}}).view()
    assert edge(body, WEB, DB)["since"] == "2026-10-21T11:53:00Z"


def test_the_charts_show_one_broken_event_across_a_restart(store):
    store.add_link_event(WEB, DB, "ok", 3.0, None, NOW - timedelta(hours=3))
    store.add_link_event(WEB, DB, "broken", None, "connection refused", NOW - timedelta(minutes=9))
    store.add_link_event(WEB, DB, "broken", None, "connection refused", NOW - timedelta(minutes=6))   # restart
    store.add_link_event(WEB, DB, "ok", 2.0, None, NOW - timedelta(minutes=4))
    store.add_link_event(WEB, DB, "ok", 2.0, None, NOW - timedelta(minutes=2))                       # restart
    assert charts(store) == [("link_broken", "Link web → db broken (connection refused)"),
                             ("link_recovered", "Link web → db recovered")]


def test_rows_are_ordered_by_time_then_id_on_sqlite_as_on_postgres(store):
    store.add_link_event(WEB, DB, "broken", None, "timeout", NOW - timedelta(minutes=2))
    store.add_link_event(WEB, DB, "ok", 3.0, None, NOW - timedelta(minutes=9))      # written later, older
    latest = store.latest_link_events()[(WEB, DB)]
    assert latest["state"] == "broken" and latest["at"] == NOW - timedelta(minutes=2)
