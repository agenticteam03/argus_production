"""T-0014 step 3: the scheduler (ARCHITECTURE §6.5, §6.6, §7.3, dependency rule 15).

Configuration is data. On each due slot the scheduler submits a scheduled health check whose identity is
`schedule_id + scheduled_for`, so a restarted scheduler never submits a slot twice. A target that is already being
investigated gets a `schedule.coalesced` audit event instead of a second run. The worker skips a scheduled request
that waited longer than the maximum queued age. The scheduler never touches detectors, the model or the graph.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone

import pytest

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.domain.model import IncidentStatus, RequestKind, TriggerKind
from argus.infrastructure.scheduler import Scheduler, load_schedules
from argus.infrastructure.worker import Worker
from test_core import ROOT, incident, make_app  # noqa: F401  (make_app = fixture)

T = "vm-166/container:argus-lab-worker"
ONE = f"""
schedules:
  - id: lab-worker-health
    cron: "*/15 * * * *"
    target: "{T}"
    reason: "scheduled health investigation"
"""
NOON = datetime(2026, 10, 7, 12, 0, 30, tzinfo=timezone.utc)


@pytest.fixture()
def inventory():
    from argus.adapters.outbound.config_adapters import YamlInventory
    return YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))


@pytest.fixture()
def store(tmp_path):
    return SqliteStore(str(tmp_path / "sched.db"))


def _scheduler(store, inventory, text=ONE):
    return Scheduler(store, load_schedules(text, inventory, min_interval_s=300))


def test_a_due_slot_submits_one_scheduled_check(store, inventory):
    results = _scheduler(store, inventory).tick(NOON)
    assert results == [("lab-worker-health", "submitted")]
    (inc,) = store.list_incidents()
    assert inc.trigger_kind == TriggerKind.scheduled and inc.request_kind == RequestKind.check
    assert str(inc.target) == T and inc.principal == "scheduler"
    assert inc.trigger_id == "sched:lab-worker-health:2026-10-07T12:00:00+00:00"


def test_the_same_slot_is_never_submitted_twice_even_after_a_restart(store, inventory):
    s = _scheduler(store, inventory)
    s.tick(NOON)
    assert s.tick(NOON + timedelta(minutes=5)) == []                       # same slot: nothing new
    store.update_incident(_close(store.list_incidents()[0]))
    restarted = _scheduler(store, inventory)
    assert restarted.tick(NOON + timedelta(minutes=5)) == [("lab-worker-health", "duplicate")]
    assert len(store.list_incidents()) == 1


def test_the_next_slot_is_submitted(store, inventory):
    s = _scheduler(store, inventory)
    s.tick(NOON)
    store.update_incident(_close(store.list_incidents()[0]))
    assert s.tick(NOON + timedelta(minutes=15)) == [("lab-worker-health", "submitted")]
    assert len(store.list_incidents()) == 2


def test_a_busy_target_is_coalesced_not_run_twice(make_app, inventory):
    app = make_app()
    busy = incident(app, T)                                                # queued: the target is being investigated
    results = Scheduler(app.store, load_schedules(ONE, inventory, min_interval_s=300)).tick(NOON)
    assert results == [("lab-worker-health", "coalesced")]
    assert len(app.store.list_incidents()) == 1
    events = [(a.event, a.detail.get("schedule_id")) for a in app.store.list_for(busy.id)]
    assert ("schedule.coalesced", "lab-worker-health") in events


def test_a_disabled_schedule_submits_nothing(store, inventory):
    text = ONE + "    enabled: false\n"
    assert _scheduler(store, inventory, text).tick(NOON) == []
    assert store.list_incidents() == []


@pytest.mark.parametrize("text, error", [
    (ONE.replace(T, "vm-166/container:not-in-inventory"), "unknown target"),
    (ONE.replace("*/15 * * * *", "every quarter hour"), "cron"),
    (ONE.replace("*/15 * * * *", "* * * * *"), "below the minimum interval"),
    (ONE + ONE.split("schedules:")[1], "duplicate schedule id"),
    (ONE.replace("    reason:", "    colour: blue\n    reason:"), "unknown field"),
])
def test_an_invalid_file_is_refused(inventory, text, error):
    with pytest.raises(ValueError, match=error):
        load_schedules(text, inventory, min_interval_s=300)


def test_the_shipped_file_is_valid_and_has_no_active_schedule(store, inventory):
    text = (ROOT / "deploy" / "scheduler" / "schedules.yaml").read_text(encoding="utf-8")
    schedules = load_schedules(text, inventory, min_interval_s=300)
    assert schedules and not any(s.enabled for s in schedules)


def test_the_worker_skips_a_scheduled_request_that_waited_too_long(make_app, inventory):
    app = make_app()
    Scheduler(app.store, load_schedules(ONE, inventory, min_interval_s=300)).tick(NOON)
    (inc,) = app.store.list_incidents()
    ran = []
    app.runner = type("R", (), {"run": lambda self, iid: ran.append(iid)})()
    w = Worker(app, worker_id="w1", max_queued_age_s=900, now=lambda: NOON + timedelta(minutes=16))
    assert w.run_once() == inc.id
    done = app.store.get_incident(inc.id)
    assert ran == [] and done.status == IncidentStatus.closed and done.closed_at is not None
    assert done.diagnosis.startswith("stale_skipped")
    assert "schedule.stale_skipped" in [a.event for a in app.store.list_for(inc.id)]


def test_a_fresh_scheduled_request_and_any_manual_request_are_run(make_app, inventory):
    app = make_app()
    Scheduler(app.store, load_schedules(ONE, inventory, min_interval_s=300)).tick(NOON)
    ran = []
    app.runner = type("R", (), {"run": lambda self, iid: ran.append(iid)})()
    w = Worker(app, worker_id="w1", max_queued_age_s=900, now=lambda: NOON + timedelta(minutes=10))
    assert w.run_once() in ran
    old_manual = incident(app, "vm-095/container:argus-lab-worker")         # manual requests never go stale
    w.now = lambda: NOON + timedelta(days=1)
    assert w.run_once() == old_manual.id and old_manual.id in ran


def test_the_scheduler_imports_no_detector_runner_graph_or_model():
    """Dependency rule 15: infrastructure/scheduler.py is a driver only."""
    tree = ast.parse((ROOT / "argus" / "infrastructure" / "scheduler.py").read_text(encoding="utf-8"))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    forbidden = ("argus.detectors", "argus.orchestration", "argus.tooling", "argus.capabilities",
                 "argus.adapters.outbound.llm", "langgraph", "openai")
    assert not [n for n in names if n.startswith(forbidden)], names


def _close(inc):
    inc.status = IncidentStatus.closed
    return inc


def test_the_scheduler_command_exists():
    from argus.__main__ import build_parser
    assert build_parser().parse_args(["scheduler"]).cmd == "scheduler"


def test_store_finds_the_active_incident_of_a_target(store):
    from test_postgres import _incident
    inc = _incident(target=T)
    store.create_incident(inc, None)
    other = _incident(target="vm-095/container:argus-lab-worker")
    store.create_incident(other, None)
    store.update_incident(_close(other))
    assert store.active_incident(inc.target).id == inc.id
    assert store.active_incident(other.target) is None
