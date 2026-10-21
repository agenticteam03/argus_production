"""T-0046 L4 follow-up (#227 review): a scheduler restart is not a link transition.

The recorder writes each link's state once at startup (ARCHITECTURE §7.3), so every deploy repeats the states it
already recorded. The stores' reads now skip a row that repeats its link's previous state (time, then id): the map's
`since` keeps the real transition time, and the incident charts and `network.link_states` show no second
`link_broken` for a link that stayed broken.
"""
from __future__ import annotations

from datetime import timedelta

from argus.adapters.outbound.config_adapters import YamlInventory
from argus.application.link_transitions import LinkTransitions
from test_t0046_l4_read_link_history import (DB, INVENTORY, NOW, WEB, Metrics, charts, edge, sample,  # noqa: F401
                                            store, topo)

CACHE = "h1/container:cache"


def restart(store, probes, at):
    """A new scheduler process: it has seen nothing, so it records every link's state once."""
    LinkTransitions(store, YamlInventory(INVENTORY), Metrics(probes), now=lambda: at).run_once()


def test_a_restart_repeats_rows_but_not_transitions(store):
    broken = {WEB: {"db": sample(0, kind="refused"), "cache": sample(1)}}
    restart(store, {WEB: {"db": sample(1), "cache": sample(1)}}, NOW - timedelta(minutes=12))
    restart(store, broken, NOW - timedelta(minutes=8))            # the link breaks: one transition
    restart(store, broken, NOW - timedelta(minutes=3))            # a deploy while it is still broken
    rows = store.link_events(WEB, NOW - timedelta(hours=1), NOW)
    assert [(r["dependency"], r["state"]) for r in rows] == [(DB, "ok"), (CACHE, "ok"), (DB, "broken")]
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
