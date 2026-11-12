"""Alert intake (ARCHITECTURE §6.1 A and D, §6.6, §7.3; ACR-0003, T-0022).

`HandleAlertNotification` turns one `AlertNotification` into durable intake. The push webhook and the pull
reconciliation both call it, so one alert gives one incident whichever way it arrived: the identity is
`fingerprint + startsAt` (§6.6). Correlation (§6.4, OP-011): an alert already recorded is a `duplicate`; one that
matches an open incident on its target and class, or the incident of the same episode that already concluded
(ACR-0004), is `attached` to it; anything else opens a new incident.
Resolution (§6.4, ACR-0005, T-0026): a `resolved` notification marks only its own occurrence resolved. When every
occurrence of an incident is resolved, a queued incident closes `resolved_externally` without a run; a running one
finishes its diagnosis (in this read-only release no write or verification is ever in flight); a concluded one is not
changed. Each step is audited.
`ReconcileFiringAlerts` reads each host's Alertmanager through `AlertSourcePort` and submits every firing alert; then
it resolves the host's occurrences whose alert is no longer active (silenced and inhibited alerts still are). A host
that cannot be read is reported, resolves nothing, and the others go on. The monitoring heartbeat (ACR-0009) never
reaches intake; while a host's heartbeat is lost (`MonitoringWatch`), that host resolves nothing either.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Literal

from argus.application.correlation import CORRELATION_WINDOW, Correlator
from argus.application.monitoring import HEARTBEAT
from argus.domain.model import (AlertNotification, AuditRecord, Incident, IncidentOutcome, IncidentStatus, RequestKind,
                                TargetRef, TriggerKind, utcnow)
from argus.ports.ports import AlertSourcePort, AlertsUnavailable

log = logging.getLogger("argus.alerts")


@dataclass(frozen=True)
class IntakeResult:
    disposition: Literal["started", "attached", "duplicate", "resolved", "ignored", "refused"]
    incident_id: str | None = None
    detail: str = ""


def alert_identity(a: AlertNotification) -> str:
    """§6.6: the same string for a pushed and a pulled copy of one alert firing. `startsAt` is truncated to
    milliseconds: the webhook's comes from Go (nanoseconds, kept to microseconds), the API v2's has milliseconds.
    `isoformat()` keeps the format of the identities already stored (".123000", or no fraction)."""
    starts = a.starts_at.replace(microsecond=a.starts_at.microsecond // 1000 * 1000)
    return f"alert:{a.fingerprint}:{starts.isoformat()}"


class HandleAlertNotification:
    def __init__(self, store, inventory, metrics, window: timedelta = CORRELATION_WINDOW,
                 now: Callable[[], datetime] = utcnow):
        """`metrics`: the port the detectors read, for the compatibility test (§6.4)."""
        self.store, self.inventory, self.now = store, inventory, now
        self.correlator = Correlator(store, metrics, window)

    def _target(self, a: AlertNotification) -> TargetRef | None:
        host = a.labels.get("argus_host")
        if not host:
            return None
        if a.labels.get("kind") in ("service", "process") and a.labels.get("name"):      # ACR-0044: TargetDown
            try:
                return TargetRef(host=host, kind=a.labels["kind"], name=a.labels["name"])
            except ValueError:
                return None
        name = a.labels.get("container") or a.labels.get("owner")
        try:
            return TargetRef(host=host, kind="container", name=name) if name else TargetRef(host=host, kind="host",
                                                                                              name=host)
        except ValueError:
            return None

    def _audit(self, incident_id: str, event: str, source: str, detail: dict) -> None:
        self.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=incident_id, at=utcnow(),
                                      category="incident", event=event, actor=source, detail=detail))

    def resolve(self, identity: str, resolved_at: datetime, source: str, via: str) -> IntakeResult:
        """Mark one occurrence resolved; when it was the incident's last firing one, settle the incident."""
        occ = self.store.resolve_alert_occurrence(identity, resolved_at)
        if occ is None:
            return IntakeResult("ignored", detail="no firing occurrence with this identity")
        inc_id = occ["incident_id"]
        firing = sum(o["status"] == "firing" for o in self.store.alert_occurrences(inc_id))
        self._audit(inc_id, "incident.alert_resolved", source,
                    {"alertname": occ["alertname"], "fingerprint": occ["fingerprint"],
                     "resolved_at": resolved_at.isoformat(), "via": via, "still_firing": firing})
        if firing == 0:
            self._all_resolved(inc_id, source)
        return IntakeResult("resolved", inc_id)

    def _all_resolved(self, incident_id: str, source: str) -> None:
        inc = self.store.get_incident(incident_id)
        before = str(inc.status) if inc else "unknown"
        closed = False
        if inc is not None and inc.status == IncidentStatus.queued:
            # No worker has claimed it: the condition stopped before any read or model call (§6.4 "Resolution").
            closed = self.store.close_queued_incident(
                incident_id, str(IncidentOutcome.resolved_externally),
                "resolved_externally: every alert of this incident resolved before an investigation started",
                self.now())
        self._audit(incident_id, "incident.alerts_all_resolved", source,
                    {"incident_status": before, "closed": closed})
        log.info("every alert of %s resolved (%s)%s", incident_id, before, ": closed resolved_externally" if closed
                 else "")

    def resolve_absent(self, host: str, active: list[AlertNotification], source: str, read_at: datetime) -> int:
        """Pull (ACR-0005): resolve the host's firing occurrences recorded before `read_at` whose alert is not among
        `active`, the host's active alerts read at `read_at`."""
        live = {alert_identity(a) for a in active}
        n = 0
        for occ in self.store.firing_occurrences(host, read_at):
            if occ["identity"] not in live:
                n += self.resolve(occ["identity"], read_at, source, via="absent_from_pull").disposition == "resolved"
        return n

    def __call__(self, a: AlertNotification, source: str) -> IntakeResult:
        if a.labels.get("alertname") == HEARTBEAT:          # ACR-0009: watched by MonitoringWatch, never an incident
            return IntakeResult("ignored", detail="monitoring heartbeat")
        if a.status == "resolved":
            return self.resolve(alert_identity(a), a.ends_at or self.now(), source, via="notification")
        target = self._target(a)
        if target is None or self.inventory.target(target) is None:
            self.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(),
                                          category="access", event="access.alert_target_not_in_inventory",
                                          actor=source, detail={"alertname": a.labels.get("alertname", ""),
                                                                "target": str(target) if target else None,
                                                                "fingerprint": a.fingerprint}))
            return IntakeResult("refused", detail=f"{target or 'no argus_host label'} is not in the inventory")
        key = alert_identity(a)
        known = self.store.incident_for_trigger(key)                 # §6.4 (1): this alert is already recorded
        if known:
            return IntakeResult("duplicate", known)
        now = self.now()
        corr = self.correlator.match(target, a.labels, a.starts_at, now)   # §6.4 (2, 3): same target, class
        if corr.incident is not None:
            inc = corr.incident
            if not self.store.add_alert_occurrence(key, inc.id, a.fingerprint, a.starts_at, a.labels, "attached",
                                                   now):
                return IntakeResult("duplicate", self.store.incident_for_trigger(key))
            version, _ = self.store.evidence_state(inc.id)
            self.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=inc.id, at=utcnow(),
                                          category="incident", event="incident.alert_attached", actor=source,
                                          detail={"alertname": a.labels.get("alertname", ""),
                                                  "fingerprint": a.fingerprint, "incident_class": corr.incident_class,
                                                  "evidence_version": version, "reason": corr.reason}))
            log.info("alert %s on %s attached to %s (%s)", a.labels.get("alertname"), target, inc.id, corr.reason)
            return IntakeResult("attached", inc.id, corr.reason)
        reason = f"alert {a.labels.get('alertname', '?')}: {a.annotations.get('summary', '')}"     # §6.4 (4)
        inc = Incident(id=f"inc_{uuid.uuid4().hex[:12]}", target=target, trigger_kind=TriggerKind.alert,
                       request_kind=RequestKind.report, reason=reason[:2000], principal=source, trigger_id=key,
                       opened_at=now)
        inc, duplicate = self.store.create_incident(inc, key)
        if duplicate:
            return IntakeResult("duplicate", inc.id)
        self.store.add_alert_occurrence(key, inc.id, a.fingerprint, a.starts_at, a.labels, "started", now)
        return IntakeResult("started", inc.id, corr.reason)


class ReconcileFiringAlerts:
    """§7.3: the primary trigger in a pull profile (ACR-0003), the outage backup in a push profile."""

    def __init__(self, source: AlertSourcePort, handle: HandleAlertNotification, hosts: list[str], watch=None):
        """`watch`: a `MonitoringWatch` (ACR-0009), or None (no heartbeat check)."""
        self.source, self.handle, self.hosts, self.watch = source, handle, hosts, watch

    def run_once(self) -> dict[str, dict[str, int | str] | str]:
        out: dict[str, dict[str, int | str] | str] = {}
        for host in self.hosts:
            try:
                alerts = self.source.firing_alerts(host)
            except AlertsUnavailable as e:
                log.warning("alerts of %s not read: %s", host, e)
                out[host] = "unavailable"
                if self.watch is not None:
                    self.watch.observe(host, None)
                continue
            counts: dict[str, int | str] = {}
            for a in alerts:
                r = self.handle(a, source=f"alertmanager@{host}")
                counts[r.disposition] = counts.get(r.disposition, 0) + 1
                if r.disposition == "started":
                    log.info("alert %s on %s: incident %s", a.labels.get("alertname"), host, r.incident_id)
            read_at = self.handle.now()
            try:
                active = self.source.active_alerts(host)
            except AlertsUnavailable as e:
                log.warning("active alerts of %s not read, nothing resolved: %s", host, e)
                counts["resolve"] = "unavailable"
                if self.watch is not None:
                    self.watch.observe(host, None)
            else:
                if self.watch is not None and self.watch.observe(host, active):
                    # ACR-0009: without a fresh heartbeat the absence of an alert is unknown, not a resolution
                    lost = self.watch.state(host).get("state") == "lost"
                    counts["resolve"] = "monitoring lost" if lost else "heartbeat not fresh"
                elif resolved := self.handle.resolve_absent(host, active, source=f"alertmanager@{host}",
                                                            read_at=read_at):
                    counts["resolved"] = resolved
            out[host] = counts
        return out
