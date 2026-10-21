"""The scheduler (T-0014, ARCHITECTURE §7.3): submits scheduled health checks; a driver only (dependency rule 15).

Configuration is data (`deploy/scheduler/schedules.yaml`). On each due slot it writes a `scheduled` `check` incident
into intake with the identity `schedule_id + scheduled_for` (§6.6), so a restarted scheduler never submits a slot
twice. A target that already has a queued or running incident gets a `schedule.coalesced` audit event on that
incident instead of a second run (§6.5 skip-if-active). It never calls a detector, the model or the graph: the worker
runs what it submits. Missed slots (scheduler down) are not replayed; only the latest due slot is submitted.

T-0022 (ACR-0003): in a pull transport profile it also runs `ReconcileFiringAlerts` every `every_s` seconds
(`reconcile_firing_alerts` in the same file): the firing alerts of each host's Alertmanager become incidents.
T-0035 (ACR-0009): `reconcile_firing_alerts.monitoring_heartbeat` turns on the heartbeat check per host (off until
every host's Prometheus has the `ArgusMonitoringHeartbeat` rule: without it, no host would ever resolve an alert).
T-0046 L3 (ACR-0025): `reconcile_firing_alerts.link_states` records the declared links' state changes on the same tick
(`application/link_transitions.py`); off until deployed. Its failure never stops the alert reconciliation.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

import yaml
from croniter import croniter

from argus.domain.model import AuditRecord, Incident, RequestKind, TargetRef, TriggerKind, utcnow

log = logging.getLogger("argus.scheduler")
FIELDS = {"id", "cron", "target", "reason", "enabled"}
RECONCILE_FIELDS = {"enabled", "every_s", "monitoring_heartbeat", "link_states"}
HEARTBEAT_FIELDS = {"enabled", "stale_after_s", "grace_s"}
LINK_STATES_FIELDS = {"enabled"}
RECONCILE_MIN_EVERY_S = 30


@dataclass(frozen=True)
class ReconcileConfig:
    enabled: bool = False
    every_s: int = 60
    heartbeat: bool = False          # ACR-0009: the monitoring heartbeat check (MonitoringWatch)
    stale_after_s: int = 180
    grace_s: int = 300
    link_states: bool = False        # ACR-0025 (T-0046 L3): record link-state changes (LinkTransitions)


def load_reconcile(text: str) -> ReconcileConfig:
    """`reconcile_firing_alerts` (§7.3): absent = off (a push profile). A bad value refuses the file."""
    item = (yaml.safe_load(text) or {}).get("reconcile_firing_alerts")
    if not item:
        return ReconcileConfig()
    extra = set(item) - RECONCILE_FIELDS
    if extra:
        raise ValueError(f"reconcile_firing_alerts: unknown field {sorted(extra)}")
    every = int(item.get("every_s", 60))
    if every < RECONCILE_MIN_EVERY_S:
        raise ValueError(f"reconcile_firing_alerts: every_s {every} is below the minimum of {RECONCILE_MIN_EVERY_S}")
    hb = item.get("monitoring_heartbeat") or {}
    if set(hb) - HEARTBEAT_FIELDS:
        raise ValueError(f"reconcile_firing_alerts.monitoring_heartbeat: unknown field {sorted(set(hb) - HEARTBEAT_FIELDS)}")
    stale, grace = int(hb.get("stale_after_s", 180)), int(hb.get("grace_s", 300))
    if stale < 2 * every or grace < stale:
        raise ValueError(f"reconcile_firing_alerts.monitoring_heartbeat: stale_after_s {stale} must be at least two "
                         f"ticks ({2 * every} s) and grace_s {grace} at least stale_after_s")
    ls = item.get("link_states") or {}
    if set(ls) - LINK_STATES_FIELDS:
        raise ValueError(f"reconcile_firing_alerts.link_states: unknown field {sorted(set(ls) - LINK_STATES_FIELDS)}")
    if ls.get("enabled") and not item.get("enabled", False):
        raise ValueError("reconcile_firing_alerts.link_states runs on the reconcile tick: enable reconcile_firing_alerts")
    return ReconcileConfig(enabled=bool(item.get("enabled", False)), every_s=every,
                           heartbeat=bool(hb.get("enabled", False)), stale_after_s=stale, grace_s=grace,
                           link_states=bool(ls.get("enabled", False)))


@dataclass(frozen=True)
class Schedule:
    id: str
    cron: str
    target: TargetRef
    reason: str
    enabled: bool = True


def load_schedules(text: str, inventory, min_interval_s: int) -> list[Schedule]:
    """Parse and validate the file; any problem refuses the whole file (the scheduler does not start)."""
    data = yaml.safe_load(text) or {}
    out: list[Schedule] = []
    for i, item in enumerate(data.get("schedules") or []):
        where = f"schedule #{i + 1} ({item.get('id', '?')})"
        extra = set(item) - FIELDS
        if extra:
            raise ValueError(f"{where}: unknown field {sorted(extra)}")
        if any(s.id == item.get("id") for s in out):
            raise ValueError(f"{where}: duplicate schedule id")
        try:
            target = TargetRef.parse(str(item["target"]))
        except (KeyError, ValueError) as e:
            raise ValueError(f"{where}: bad target: {e}")
        if inventory.target(target) is None:
            raise ValueError(f"{where}: unknown target {target} (not in the inventory)")
        cron = str(item.get("cron", ""))
        if not croniter.is_valid(cron):
            raise ValueError(f"{where}: invalid cron expression {cron!r}")
        it = croniter(cron, datetime(2026, 1, 1))
        slots = [it.get_next(datetime) for _ in range(50)]     # the smallest gap counts (e.g. "0,5 * * * *")
        gap = min((b - a).total_seconds() for a, b in zip(slots, slots[1:]))
        if gap < min_interval_s:
            raise ValueError(f"{where}: runs every {int(gap)} s, below the minimum interval of {min_interval_s} s")
        out.append(Schedule(id=str(item["id"]), cron=cron, target=target,
                            reason=str(item.get("reason", "scheduled health investigation"))[:2000],
                            enabled=bool(item.get("enabled", True))))
    return out


class Scheduler:
    def __init__(self, store, schedules: list[Schedule], reconcile=None, reconcile_every_s: int = 60, links=None):
        self.store = store
        self.schedules = schedules
        self.reconcile, self.reconcile_every_s = reconcile, reconcile_every_s   # ReconcileFiringAlerts or None
        self.links = links                     # LinkTransitions or None (T-0046 L3): on the reconcile tick
        self._last: dict[str, datetime] = {}

    def tick(self, now: datetime) -> list[tuple[str, str]]:
        """Submit the latest due slot of every enabled schedule not yet handled by this process."""
        results = []
        for s in self.schedules:
            if not s.enabled:
                continue
            slot = croniter(s.cron, now).get_prev(datetime)
            if self._last.get(s.id) == slot:
                continue
            self._last[s.id] = slot
            results.append((s.id, self._submit(s, slot, now)))
        return results

    def _submit(self, s: Schedule, slot: datetime, now: datetime) -> str:
        key = f"sched:{s.id}:{slot.isoformat()}"
        active = self.store.active_incident(s.target)
        if active is not None:
            if active.trigger_id == key:
                return "duplicate"
            self.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=active.id, at=utcnow(),
                                          category="incident", event="schedule.coalesced", actor="scheduler",
                                          detail={"schedule_id": s.id, "scheduled_for": slot.isoformat()}))
            log.info("%s %s: %s is busy (%s), coalesced", s.id, slot.isoformat(), s.target, active.id)
            return "coalesced"
        inc = Incident(id=f"inc_{uuid.uuid4().hex[:12]}", target=s.target, trigger_kind=TriggerKind.scheduled,
                       request_kind=RequestKind.check, reason=s.reason, principal="scheduler", trigger_id=key,
                       opened_at=now)
        inc, duplicate = self.store.create_incident(inc, key)
        log.info("%s %s: %s %s", s.id, slot.isoformat(), "duplicate" if duplicate else "submitted", inc.id)
        return "duplicate" if duplicate else "submitted"

    def run_forever(self, stop: threading.Event, every_s: float = 15.0) -> None:
        next_reconcile = time.monotonic()
        while not stop.is_set():
            try:
                self.tick(utcnow())
            except Exception:                  # a database hiccup must not kill the scheduler; next tick retries
                log.exception("tick failed")
            if self.reconcile is not None and time.monotonic() >= next_reconcile:
                next_reconcile = time.monotonic() + self.reconcile_every_s
                try:
                    log.info("reconcile firing alerts: %s", self.reconcile.run_once())
                except Exception:              # same rule: the next pass retries
                    log.exception("reconcile failed")
                if self.links is not None:     # T-0046 L3: after the alerts, and never in their way
                    try:
                        log.info("link states: %s", self.links.run_once())
                    except Exception:
                        log.exception("link states failed")
            stop.wait(every_s)

