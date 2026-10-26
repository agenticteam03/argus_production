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
ACR-0018 (`audit_chain` in the same file): at startup and every `every_s` seconds it verifies the audit hash chain and
records the result as a `security` audit event (`security.audit_chain_verified` or `security.audit_chain_broken`).
ACR-0018 step 5 (`audit_digest` in the same file, off until the audit digest key and the store exist): every `every_s`
seconds `AuditDigestJob` (`infrastructure/audit_digest.py`) signs and ships the digest of each closed day.
ACR-0018 §18 (`security_alerts` in the same file, off by default): every `every_s` seconds `SecurityAlerts`
(`infrastructure/security_alerts.py`) posts the new security events to the home host's Alertmanager, which routes them
to the team.
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
AUDIT_CHAIN_FIELDS = {"enabled", "every_s"}
AUDIT_CHAIN_MIN_EVERY_S = 3600          # the whole chain is read: at most hourly
AUDIT_DIGEST_FIELDS = {"enabled", "every_s"}
AUDIT_DIGEST_MIN_EVERY_S = 3600         # it reads the whole chain too
SECURITY_ALERTS_FIELDS = {"enabled", "every_s", "host"}
SECURITY_ALERTS_MIN_EVERY_S = 30


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


def load_audit_chain(text: str) -> int | None:
    """`audit_chain` (ACR-0018): the seconds between two verifications of the audit hash chain; None = off."""
    item = (yaml.safe_load(text) or {}).get("audit_chain")
    if not item:
        return None
    extra = set(item) - AUDIT_CHAIN_FIELDS
    if extra:
        raise ValueError(f"audit_chain: unknown field {sorted(extra)}")
    every = int(item.get("every_s", 86400))
    if every < AUDIT_CHAIN_MIN_EVERY_S:
        raise ValueError(f"audit_chain: every_s {every} is below the minimum of {AUDIT_CHAIN_MIN_EVERY_S}")
    return every if item.get("enabled", False) else None


def load_audit_digest(text: str) -> int | None:
    """`audit_digest` (ACR-0018 step 5): the seconds between two runs of the signed daily digest job; None = off."""
    item = (yaml.safe_load(text) or {}).get("audit_digest")
    if not item:
        return None
    extra = set(item) - AUDIT_DIGEST_FIELDS
    if extra:
        raise ValueError(f"audit_digest: unknown field {sorted(extra)}")
    every = int(item.get("every_s", 86400))
    if every < AUDIT_DIGEST_MIN_EVERY_S:
        raise ValueError(f"audit_digest: every_s {every} is below the minimum of {AUDIT_DIGEST_MIN_EVERY_S}")
    return every if item.get("enabled", False) else None


class AuditChainCheck:
    """ACR-0018 §17.1 layer 13: verify the whole chain and record the result. A broken chain is logged as an error and
    recorded as `security.audit_chain_broken` (the first problems, never a body); an alert on it follows when the
    team's alert route exists (§18)."""

    def __init__(self, store):
        self.store = store

    def run_once(self) -> str:
        from argus.domain.audit_chain import verify
        chained, before, problems = verify(self.store.audit_chain())
        event = "security.audit_chain_broken" if problems else "security.audit_chain_verified"
        detail = {"chained": chained, "before_chain": before, "problems": len(problems), "first": problems[:5]}
        if problems:
            log.error("AUDIT CHAIN BROKEN: %d problem(s), first: %s", len(problems), problems[0])
        self.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(),
                                      category="security", event=event, actor="scheduler", detail=detail))
        return f"{event}: {chained} chained, {before} before, {len(problems)} problem(s)"


def load_security_alerts(text: str, inventory) -> tuple[int, str] | None:
    """`security_alerts` (ACR-0018 §18): (seconds between two passes, the Alertmanager URL of `host`); None = off."""
    item = (yaml.safe_load(text) or {}).get("security_alerts")
    if not item:
        return None
    extra = set(item) - SECURITY_ALERTS_FIELDS
    if extra:
        raise ValueError(f"security_alerts: unknown field {sorted(extra)}")
    every = int(item.get("every_s", 60))
    if every < SECURITY_ALERTS_MIN_EVERY_S:
        raise ValueError(f"security_alerts: every_s {every} is below the minimum of {SECURITY_ALERTS_MIN_EVERY_S}")
    if not item.get("enabled", False):
        return None
    info = inventory.host(str(item.get("host", "")))
    if info is None or not info.alertmanager:
        raise ValueError(f"security_alerts: host {item.get('host')!r} is not an inventory host with an alertmanager")
    return every, info.alertmanager


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
    def __init__(self, store, schedules: list[Schedule], reconcile=None, reconcile_every_s: int = 60,
                 chain_check=None, chain_every_s: int = 86400, links=None, digest_job=None,
                 digest_every_s: int = 86400, alerts_job=None, alerts_every_s: int = 60):
        self.store = store
        self.schedules = schedules
        self.reconcile, self.reconcile_every_s = reconcile, reconcile_every_s   # ReconcileFiringAlerts or None
        self.chain_check, self.chain_every_s = chain_check, chain_every_s       # AuditChainCheck or None (ACR-0018)
        self.links = links                     # LinkTransitions or None (T-0046 L3): on the reconcile tick
        self.digest_job, self.digest_every_s = digest_job, digest_every_s       # AuditDigestJob or None (ACR-0018)
        self.alerts_job, self.alerts_every_s = alerts_job, alerts_every_s       # SecurityAlerts or None (ACR-0018 §18)
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
        next_reconcile = next_chain = next_digest = next_alerts = time.monotonic()
        while not stop.is_set():
            if self.chain_check is not None and time.monotonic() >= next_chain:
                next_chain = time.monotonic() + self.chain_every_s
                try:
                    log.info("audit chain: %s", self.chain_check.run_once())
                except Exception:              # the next pass retries; a failure to verify is not a broken chain
                    log.exception("audit chain check failed")
            if self.digest_job is not None and time.monotonic() >= next_digest:
                next_digest = time.monotonic() + self.digest_every_s
                try:
                    log.info("audit digest: %s", self.digest_job.run_once())
                except Exception:              # the next run starts from the first day not shipped
                    log.exception("audit digest failed")
            if self.alerts_job is not None and time.monotonic() >= next_alerts:
                next_alerts = time.monotonic() + self.alerts_every_s
                try:                           # after the chain check and the digest: their events alert this pass
                    log.info("security alerts: %s", self.alerts_job.run_once())
                except Exception:              # Alertmanager down: the next pass sends the same rows again
                    log.exception("security alerts failed")
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

