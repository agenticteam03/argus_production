"""T-0035 / ACR-0009: a monitoring heartbeat per host (ARCHITECTURE §7.3, §6.4 "Resolution").

Every host's Prometheus fires `ArgusMonitoringHeartbeat` while it evaluates rules. On every reconcile tick Argus looks
for it in the host's active alerts (silenced and inhibited included). It is **fresh** when listed with the host's
`argus_host`, `endsAt` in the future and `updatedAt` no older than `stale_after`: a copy that is still listed but no
longer renewed is not fresh. No fresh heartbeat for `stale_after` (or none within the startup grace) = **lost**: one
incident per host and loss episode, `monitoring_blind_spot`, RB-014, closed at once `undiagnosable` and escalated, no
run, no model, no read of the host; and the host resolves nothing while lost. Two consecutive fresh ticks = recovered
(also to leave the startup grace). A planned stop is declared (`maintenance`), never inferred from a silence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from argus.application.monitoring import HEARTBEAT, MonitoringConfig, MonitoringWatch
from argus.domain.model import AlertNotification, IncidentOutcome, IncidentStatus
from argus.ports.ports import AlertsUnavailable
from test_core import make_app  # noqa: F401  (fixture)
from test_op011_correlation import _probe

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
HOST = "vm-166"
CFG = MonitoringConfig(stale_after=timedelta(minutes=3), grace=timedelta(minutes=5))


def beat(updated: datetime, ends: datetime | None = None, host: str = HOST) -> AlertNotification:
    return AlertNotification(fingerprint=f"hb-{host}", status="firing", starts_at=T0 - timedelta(hours=1),
                             ends_at=ends or updated + timedelta(minutes=4), updated_at=updated,
                             labels={"alertname": HEARTBEAT, "argus_host": host},
                             annotations={"summary": f"monitoring heartbeat of {host}"})


class Clock:
    def __init__(self, t: datetime):
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def tick(self, minutes: float = 1) -> datetime:
        self.t += timedelta(minutes=minutes)
        return self.t


def _watch(app, clock, ready=lambda host: None):
    return MonitoringWatch(app.store, CFG, now=clock, prometheus_ready=ready)


def _audited(app) -> list:
    seen, real = [], app.store.append
    app.store.append = lambda rec: seen.append(rec) or real(rec)
    return seen


def _monitoring_incidents(app):
    return [i for i in app.store.list_incidents(200) if i.trigger_id.startswith("monitoring:")]


def _alive(watch, clock, ticks=2):
    """Leave the startup grace: two consecutive fresh ticks."""
    for _ in range(ticks):
        assert watch.observe(HOST, [beat(clock())]) is False
        clock.tick()


# --- freshness --------------------------------------------------------------------------------------------------------
def test_a_renewed_heartbeat_keeps_the_host_alive(make_app):
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    _alive(w, clock)
    for _ in range(10):
        assert w.observe(HOST, [beat(clock() - timedelta(seconds=50))]) is False
        clock.tick()
    assert w.state(HOST)["state"] == "alive" and _monitoring_incidents(app) == []


def test_a_copy_still_listed_but_not_renewed_is_not_fresh(make_app):
    """Juan's #108 note: the important case. Alertmanager keeps listing the alert until its endsAt; reading the kept
    copy again is not a new heartbeat."""
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    _alive(w, clock)
    last = clock() - timedelta(seconds=30)
    kept = beat(last, ends=last + timedelta(minutes=30))            # listed for 30 more minutes, never renewed
    lost_at = None
    for i in range(6):
        if w.observe(HOST, [kept]) and lost_at is None:
            lost_at = clock()
        clock.tick()
    assert lost_at is not None and lost_at - last <= CFG.stale_after + timedelta(minutes=1)
    assert len(_monitoring_incidents(app)) == 1


def test_an_expired_heartbeat_is_not_fresh(make_app):
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    _alive(w, clock)
    expired = beat(clock(), ends=clock() - timedelta(seconds=1))
    for _ in range(4):
        w.observe(HOST, [expired])
        clock.tick()
    assert w.state(HOST)["state"] == "lost"


def test_another_hosts_heartbeat_does_not_count(make_app):
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    _alive(w, clock)
    for _ in range(4):
        w.observe(HOST, [beat(clock(), host="vm-095")])
        clock.tick()
    assert w.state(HOST)["state"] == "lost"


def test_a_silenced_heartbeat_is_still_read():
    """The heartbeat is looked up in `active_alerts` (silenced and inhibited included), never `firing_alerts`."""
    from argus.application.alerts import ReconcileFiringAlerts
    import inspect
    src = inspect.getsource(ReconcileFiringAlerts.run_once)
    assert "self.watch.observe(host, active" in src


# --- loss -------------------------------------------------------------------------------------------------------------
def test_a_lost_heartbeat_opens_one_escalated_incident_with_no_run(make_app):
    app, clock = make_app(), Clock(T0)
    audited = _audited(app)
    w = _watch(app, clock, ready=lambda host: False)
    _alive(w, clock)
    for _ in range(8):
        w.observe(HOST, [])
        clock.tick()
    incs = _monitoring_incidents(app)
    assert len(incs) == 1
    inc = incs[0]
    assert inc.status == IncidentStatus.escalated and inc.outcome == IncidentOutcome.undiagnosable
    assert inc.incident_class == "monitoring_blind_spot" and "Host monitoring unavailable" in inc.findings
    assert str(inc.target) == f"{HOST}/host:{HOST}" and inc.closed_at is not None
    assert "RB-014" in inc.diagnosis and "Prometheus not reachable from Argus" in inc.diagnosis
    assert app.store.claim_next_queued("worker-1") is None                              # nothing for a worker
    lost = [a for a in audited if a.event == "monitoring.lost"]
    assert len(lost) == 1 and lost[0].incident_id == inc.id


def test_the_cause_says_what_was_observed(make_app):
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock, ready=lambda host: True)
    _alive(w, clock)
    for _ in range(5):
        w.observe(HOST, [])                                             # Alertmanager answers, heartbeat missing
        clock.tick()
    assert "heartbeat lost" in _monitoring_incidents(app)[0].diagnosis

    other = "vm-095"
    for _ in range(2):
        w.observe(other, [beat(clock(), host=other)])
        clock.tick()
    for _ in range(5):
        w.observe(other, None)                                          # Alertmanager does not answer
        clock.tick()
    inc = next(i for i in _monitoring_incidents(app) if i.target.host == other)
    assert "monitoring cannot be read" in inc.diagnosis


def test_one_incident_per_episode_even_across_a_scheduler_restart(make_app):
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    _alive(w, clock)
    for _ in range(5):
        w.observe(HOST, [])
        clock.tick()
    restarted = _watch(app, clock)                                      # the state is in the store
    for _ in range(5):
        restarted.observe(HOST, [])
        clock.tick()
    assert len(_monitoring_incidents(app)) == 1


# --- recovery and a new episode -----------------------------------------------------------------------------------------
def test_two_fresh_ticks_recover_and_a_later_loss_is_a_new_episode(make_app):
    app, clock = make_app(), Clock(T0)
    audited = _audited(app)
    w = _watch(app, clock)
    _alive(w, clock)
    for _ in range(5):
        w.observe(HOST, [])
        clock.tick()
    assert w.observe(HOST, [beat(clock())]) is True                      # one fresh tick: still lost
    clock.tick()
    assert w.observe(HOST, [beat(clock())]) is False                     # the second: recovered
    first = _monitoring_incidents(app)[0]
    rec = [a for a in audited if a.event == "monitoring.recovered"]
    assert len(rec) == 1 and rec[0].incident_id == first.id
    clock.tick()
    for _ in range(5):
        w.observe(HOST, [])
        clock.tick()
    assert len(_monitoring_incidents(app)) == 2


def test_one_late_fresh_tick_after_a_restart_does_not_leave_the_grace(make_app):
    """Juan's #108 note: two consecutive fresh ticks also to leave the startup grace."""
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    assert w.observe(HOST, [beat(clock())]) is False                     # within the grace: not lost
    clock.tick()
    assert w.observe(HOST, []) is True                                   # not fresh: resolve nothing
    clock.tick()
    assert w.state(HOST)["state"] == "starting" and _monitoring_incidents(app) == []


def test_never_seen_after_the_grace_is_lost(make_app):
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    states = []
    for _ in range(7):
        assert w.observe(HOST, []) is True                               # never fresh: never resolves
        states.append(w.state(HOST)["state"])
        clock.tick()
    assert states[:5] == ["starting"] * 5 and states[-1] == "lost"
    assert len(_monitoring_incidents(app)) == 1


# --- no resolution while lost ---------------------------------------------------------------------------------------------
class Source:
    def __init__(self):
        self.firing, self.active = [], []

    def firing_alerts(self, host):
        if self.firing is None:
            raise AlertsUnavailable("down")
        return [a for a in self.firing if a.labels.get("alertname") != HEARTBEAT]

    def active_alerts(self, host):
        if self.active is None:
            raise AlertsUnavailable("down")
        return list(self.active)


def _reconcile(app, src, watch):
    from argus.application.alerts import HandleAlertNotification, ReconcileFiringAlerts
    from test_core import FakeMetrics
    from test_op011_correlation import SC03
    handle = HandleAlertNotification(app.store, app.inventory, FakeMetrics(SC03), now=watch.now)
    return ReconcileFiringAlerts(src, handle, [HOST], watch=watch)


def test_an_application_incident_stays_open_while_monitoring_is_lost(make_app):
    """Juan's #108 note: a queued application incident when the heartbeat is lost stays open."""
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    src = Source()
    r = _reconcile(app, src, w)
    probe = _probe(starts=T0)
    src.firing = [probe]
    src.active = [probe, beat(clock())]
    r.run_once()
    clock.tick()
    src.active = [probe, beat(clock())]
    r.run_once()                                                         # alive, the app incident queued
    app_inc = next(i for i in app.store.list_incidents(50) if i.trigger_id.startswith("alert:"))
    src.firing, src.active = [], []                                      # Prometheus dead: alerts expired, no beat
    clock.tick()
    assert r.run_once()[HOST]["resolve"] == "heartbeat not fresh"        # not lost yet, and nothing resolved
    for _ in range(5):
        clock.tick()
        out = r.run_once()
    assert app.store.get_incident(app_inc.id).status == IncidentStatus.queued
    assert {o["status"] for o in app.store.alert_occurrences(app_inc.id)} == {"firing"}
    assert out[HOST]["resolve"] == "monitoring lost"
    src.active = [beat(clock())]
    clock.tick()
    r.run_once()
    src.active = [beat(clock())]
    clock.tick()
    r.run_once()                                                         # recovered: absence counts again
    assert {o["status"] for o in app.store.alert_occurrences(app_inc.id)} == {"resolved"}


def test_the_heartbeat_never_reaches_intake(make_app):
    from argus.application.alerts import HandleAlertNotification
    from test_core import FakeMetrics
    app = make_app()
    h = HandleAlertNotification(app.store, app.inventory, FakeMetrics())
    assert h(beat(T0), source="alertmanager@vm-166").disposition == "ignored"
    assert app.store.list_incidents(10) == []


# --- maintenance --------------------------------------------------------------------------------------------------------
def test_maintenance_opens_nothing_and_expires(make_app):
    app, clock = make_app(), Clock(T0)
    audited = _audited(app)
    w = _watch(app, clock)
    _alive(w, clock)
    w.maintenance(HOST, minutes=10, who="conantkd")
    for _ in range(8):
        w.observe(HOST, [])
        clock.tick()
    assert _monitoring_incidents(app) == []
    assert [a for a in audited if a.event == "monitoring.lost_in_maintenance"]
    assert [a for a in audited if a.event == "monitoring.maintenance"][0].actor == "conantkd"
    for _ in range(4):
        w.observe(HOST, [])
        clock.tick()
    assert len(_monitoring_incidents(app)) == 1                          # still lost after it ended


@pytest.mark.parametrize("minutes", [0, -5, 241])
def test_maintenance_is_bounded(make_app, minutes):
    app, clock = make_app(), Clock(T0)
    with pytest.raises(ValueError):
        _watch(app, clock).maintenance(HOST, minutes=minutes, who="conantkd")


# --- the rule and the adapter ---------------------------------------------------------------------------------------------
def test_the_rule_is_the_same_on_every_host():
    import yaml
    from pathlib import Path
    rules = yaml.safe_load((Path(__file__).resolve().parents[1] / "deploy" / "monitoring" / "alerts.yml")
                           .read_text(encoding="utf-8"))
    hb = [r for g in rules["groups"] for r in g["rules"] if r.get("alert") == HEARTBEAT]
    assert len(hb) == 1 and hb[0]["expr"] == 'count by (argus_host) (up{argus_host!=""}) > 0'
    assert "for" not in hb[0]                                            # fires at once


def test_the_adapter_reads_updated_at():
    import httpx
    from argus.adapters.outbound.alerts_alertmanager import AlertmanagerSource
    body = [{"fingerprint": "hb", "startsAt": "2026-10-13T11:00:00.000Z", "endsAt": "2026-10-13T12:04:00.000Z",
             "updatedAt": "2026-10-13T12:00:00.123Z", "labels": {"alertname": HEARTBEAT, "argus_host": HOST},
             "annotations": {}}]
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    a = AlertmanagerSource({HOST: "http://am"}, client=client).active_alerts(HOST)[0]
    assert a.updated_at == datetime(2026, 10, 13, 12, 0, 0, 123000, tzinfo=timezone.utc)


# --- configuration and wiring -------------------------------------------------------------------------------------------
def test_the_heartbeat_check_is_configured():
    from pathlib import Path
    from argus.infrastructure.scheduler import load_reconcile
    cfg = load_reconcile((Path(__file__).resolve().parents[1] / "deploy" / "scheduler" / "schedules.yaml")
                         .read_text(encoding="utf-8"))
    assert cfg.heartbeat is True and (cfg.stale_after_s, cfg.grace_s) == (180, 300)   # step 2: the rule is deployed
    off = load_reconcile("reconcile_firing_alerts: {enabled: true, every_s: 60}")
    assert off.heartbeat is False                                       # absent = off
    with pytest.raises(ValueError):                                    # one tick is not enough to judge a renewal
        load_reconcile("reconcile_firing_alerts: {enabled: true, every_s: 60, "
                       "monitoring_heartbeat: {enabled: true, stale_after_s: 60}}")
    with pytest.raises(ValueError):
        load_reconcile("reconcile_firing_alerts: {enabled: true, monitoring_heartbeat: {enabled: true, x: 1}}")


def test_the_maintenance_command_is_bounded_and_needs_a_known_host():
    from argus.__main__ import build_parser
    a = build_parser().parse_args(["monitoring", "maintenance", "vm-166", "--minutes", "30", "--as", "conantkd"])
    assert (a.host, a.minutes, a.who) == ("vm-166", 30, "conantkd")
    with pytest.raises(SystemExit):
        build_parser().parse_args(["monitoring", "maintenance", "vm-166", "--minutes", "30"])   # --as is required


def test_a_loss_is_notified_like_any_escalation(make_app):
    """§15.2: every escalation enqueues a notification (`<incident>:escalation`); the loss incident is stored already
    escalated, so the watch enqueues it itself — once per episode, also across a restart."""
    app, clock = make_app(), Clock(T0)
    w = _watch(app, clock)
    _alive(w, clock)
    for _ in range(6):
        w.observe(HOST, [])
        clock.tick()
    _watch(app, clock).observe(HOST, [])                                 # a restarted scheduler
    inc = _monitoring_incidents(app)[0]
    notes = [n for n in app.store.notifications() if n["key"] == f"{inc.id}:escalation"]
    assert len(notes) == 1
    p = notes[0]["payload"]
    assert p["incident_id"] == inc.id and p["outcome"] == "undiagnosable" and p["route"] == "channel:operators"
    assert "Host monitoring unavailable" in p["diagnosis"]
