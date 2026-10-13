"""Monitoring heartbeat per host (ARCHITECTURE §7.3, §6.4 "Resolution"; ACR-0009, T-0035).

Every host's Prometheus fires `ArgusMonitoringHeartbeat` while it evaluates rules. On every reconcile tick
`MonitoringWatch.observe` looks for it in the host's active alerts (silenced and inhibited included, so a silence never
hides a loss). It is fresh when listed with the host's own `argus_host`, `endsAt` in the future and `updatedAt` no
older than `stale_after`: a copy Alertmanager still lists but nobody renews is not fresh.

- **Lost:** no fresh heartbeat for `stale_after` (judged from the last renewal seen), or none within the startup
  `grace`. One incident per host and loss episode on the host target, class `monitoring_blind_spot`, RB-014, closed at
  once `undiagnosable` and escalated: no worker run, no model call, no read of the host (its idempotency key is
  `monitoring:<host>:<episode start>`). One bounded readiness read of the host's Prometheus refines the cause.
- **Recovered:** two consecutive fresh ticks; also needed to leave the startup grace, so one late renewal after a
  scheduler restart neither opens an incident nor ends the grace.
- On a tick without a fresh heartbeat (lost, or not yet), the host resolves nothing (the caller skips
  `resolve_absent`): the absence of its alerts is unknown, not a resolution (§6.4).
- A planned stop is declared (`maintenance`, at most 240 minutes, audited), never inferred from a silence: a loss in
  it is audited but opens no incident; one still present after it ends does.

The state per host is stored, so a scheduler restart neither opens a second incident for an episode nor forgets one.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from argus.domain.model import (AlertNotification, AuditRecord, Incident, IncidentOutcome, IncidentStatus, RequestKind,
                                TargetRef, TriggerKind, utcnow)

log = logging.getLogger("argus.monitoring")

HEARTBEAT = "ArgusMonitoringHeartbeat"
MAX_MAINTENANCE_MIN = 240
FRESH_TICKS = 2


@dataclass(frozen=True)
class MonitoringConfig:
    stale_after: timedelta = timedelta(minutes=3)
    grace: timedelta = timedelta(minutes=5)


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() if t else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class MonitoringWatch:
    def __init__(self, store, config: MonitoringConfig = MonitoringConfig(),
                 now: Callable[[], datetime] = utcnow,
                 prometheus_ready: Callable[[str], bool | None] = lambda host: None):
        """`prometheus_ready(host)`: one bounded readiness read of the host's Prometheus (True / False / None =
        not checked); it only refines the recorded cause."""
        self.store, self.config, self.now, self.ready = store, config, now, prometheus_ready
        self._this_process: set[str] = set()

    # --- state ------------------------------------------------------------------------------------------------------
    def state(self, host: str) -> dict:
        return self.store.monitoring_state(host) or {}

    def _save(self, host: str, st: dict) -> None:
        self.store.save_monitoring_state(host, st)

    def _audit(self, incident_id: str | None, event: str, actor: str, detail: dict) -> None:
        self.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=incident_id, at=utcnow(),
                                      category="incident", event=event, actor=actor, detail=detail))

    def _fresh(self, host: str, active: list[AlertNotification] | None, now: datetime) -> datetime | None:
        """The renewal time of the host's fresh heartbeat, or None."""
        best = None
        for a in active or []:
            if a.labels.get("alertname") != HEARTBEAT or a.labels.get("argus_host") != host:
                continue
            if a.ends_at is None or a.ends_at <= now or a.updated_at is None:
                continue
            if now - a.updated_at > self.config.stale_after:
                continue
            best = max(best, a.updated_at) if best else a.updated_at
        return best

    # --- one tick ---------------------------------------------------------------------------------------------------
    def observe(self, host: str, active: list[AlertNotification] | None) -> bool:
        """One reconcile tick for `host`. `active`: its active alerts, or None when they could not be read. Returns
        True when the absence of the host's alerts is unknown on this tick (no fresh heartbeat, or lost): the caller
        then resolves nothing for it."""
        now = self.now()
        st = self.state(host)
        if host not in self._this_process:                    # this process starts watching the host
            self._this_process.add(host)
            if st.get("state") != "lost":                      # a lost episode goes on across a restart
                st = {**st, "state": "starting", "started_at": _iso(now), "fresh_ticks": 0}
        renewed = self._fresh(host, active, now)
        if renewed is not None:
            st["fresh_ticks"] = int(st.get("fresh_ticks", 0)) + 1
            last = _dt(st.get("last_beat_at"))
            st["last_beat_at"] = _iso(max(renewed, last) if last else renewed)
        else:
            st["fresh_ticks"] = 0
        state = st.get("state", "starting")
        if state == "starting":
            if st["fresh_ticks"] >= FRESH_TICKS:
                st["state"] = "alive"
            elif now - _dt(st["started_at"]) >= self.config.grace:
                self._lose(host, st, now, active, "no heartbeat since the watch started")
        elif state == "alive":
            last = _dt(st.get("last_beat_at"))
            if renewed is None and (last is None or now - last > self.config.stale_after):
                self._lose(host, st, now, active, "no fresh heartbeat")
        elif state == "lost":
            if st["fresh_ticks"] >= FRESH_TICKS:
                st["state"] = "alive"
                self._audit(st.get("incident_id"), "monitoring.recovered", "scheduler",
                            {"host": host, "episode_start": st.get("episode_start"), "recovered_at": _iso(now)})
                log.info("monitoring of %s recovered (episode from %s)", host, st.get("episode_start"))
            elif st.get("incident_id") is None and not self._in_maintenance(st, now):
                self._open(host, st, now, active)               # a loss that outlived its maintenance window
        self._save(host, st)
        return st["state"] == "lost" or renewed is None

    def _in_maintenance(self, st: dict, now: datetime) -> bool:
        until = _dt(st.get("maintenance_until"))
        return until is not None and now < until

    def _lose(self, host: str, st: dict, now: datetime, active, why: str) -> None:
        st.update({"state": "lost", "episode_start": _iso(now), "incident_id": None, "why": why})
        log.warning("monitoring of %s lost: %s", host, why)
        if self._in_maintenance(st, now):
            self._audit(None, "monitoring.lost_in_maintenance", "scheduler",
                        {"host": host, "episode_start": st["episode_start"], "until": st.get("maintenance_until")})
            return
        self._open(host, st, now, active)

    def _cause(self, host: str, active) -> str:
        cause = ("monitoring cannot be read: check the host's Alertmanager and the transport" if active is None else
                 "heartbeat lost: check the host's Prometheus rule evaluation and alert delivery")
        ready = self.ready(host)
        if ready is False:
            cause += "; Prometheus not reachable from Argus: cause to be confirmed"
        elif ready is True:
            cause += "; the host's Prometheus answers its readiness check"
        return cause

    def _open(self, host: str, st: dict, now: datetime, active) -> None:
        cause = self._cause(host, active)
        key = f"monitoring:{host}:{st['episode_start']}"
        inc = Incident(
            id=f"inc_{uuid.uuid4().hex[:12]}", target=TargetRef(host=host, kind="host", name=host),
            trigger_kind=TriggerKind.system, request_kind=RequestKind.report,
            reason=f"monitoring heartbeat of {host} lost", principal="scheduler", trigger_id=key,
            incident_class="monitoring_blind_spot", status=IncidentStatus.escalated,
            outcome=IncidentOutcome.undiagnosable, findings=["Host monitoring unavailable"],
            diagnosis=(f"Host monitoring unavailable on {host} since {st['episode_start']}: {cause}. No investigation "
                       f"was run (ACR-0009): escalated for a human. Runbook RB-014."),
            opened_at=now, closed_at=now)
        inc, duplicate = self.store.create_incident(inc, key)
        st["incident_id"] = inc.id
        if not duplicate:
            self._audit(inc.id, "monitoring.lost", "scheduler",
                        {"host": host, "episode_start": st["episode_start"], "cause": cause})
            log.warning("monitoring of %s lost: incident %s (%s)", host, inc.id, cause)

    # --- maintenance --------------------------------------------------------------------------------------------------
    def maintenance(self, host: str, minutes: int, who: str) -> datetime:
        if not isinstance(minutes, int) or not 0 < minutes <= MAX_MAINTENANCE_MIN:
            raise ValueError(f"maintenance: minutes must be 1..{MAX_MAINTENANCE_MIN}")
        until = self.now() + timedelta(minutes=minutes)
        st = self.state(host)
        st["maintenance_until"] = _iso(until)
        self._save(host, st)
        self._audit(None, "monitoring.maintenance", who, {"host": host, "until": _iso(until), "minutes": minutes})
        return until
