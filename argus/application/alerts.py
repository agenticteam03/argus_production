"""Alert intake (ARCHITECTURE §6.1 A and D, §6.6, §7.3; ACR-0003, T-0022).

`HandleAlertNotification` turns one `AlertNotification` into durable intake. The push webhook and the pull
reconciliation both call it, so one alert gives one incident whichever way it arrived: the identity is
`fingerprint + startsAt` (§6.6). Correlation (§6.4, OP-011): an alert already recorded is a `duplicate`; one that
matches an open incident on its target and class, or the incident of the same episode that already concluded
(ACR-0004), is `attached` to it; anything else opens a new incident.
`ReconcileFiringAlerts` reads each host's Alertmanager through `AlertSourcePort`
and submits every firing alert; a host that cannot be read is reported and the others go on.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Literal

from argus.application.correlation import CORRELATION_WINDOW, Correlator
from argus.domain.model import (AlertNotification, AuditRecord, Incident, RequestKind, TargetRef, TriggerKind,
                                utcnow)
from argus.ports.ports import AlertSourcePort, AlertsUnavailable

log = logging.getLogger("argus.alerts")


@dataclass(frozen=True)
class IntakeResult:
    disposition: Literal["started", "attached", "duplicate", "ignored", "refused"]
    incident_id: str | None = None
    detail: str = ""


def alert_identity(a: AlertNotification) -> str:
    """§6.6: the same string for a pushed and a pulled copy of one alert firing."""
    return f"alert:{a.fingerprint}:{a.starts_at.isoformat()}"


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
        name = a.labels.get("container") or a.labels.get("owner")
        try:
            return TargetRef(host=host, kind="container", name=name) if name else TargetRef(host=host, kind="host",
                                                                                              name=host)
        except ValueError:
            return None

    def __call__(self, a: AlertNotification, source: str) -> IntakeResult:
        if a.status != "firing":
            return IntakeResult("ignored", detail="not firing")
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

    def __init__(self, source: AlertSourcePort, handle: HandleAlertNotification, hosts: list[str]):
        self.source, self.handle, self.hosts = source, handle, hosts

    def run_once(self) -> dict[str, dict[str, int] | str]:
        out: dict[str, dict[str, int] | str] = {}
        for host in self.hosts:
            try:
                alerts = self.source.firing_alerts(host)
            except AlertsUnavailable as e:
                log.warning("alerts of %s not read: %s", host, e)
                out[host] = "unavailable"
                continue
            counts: dict[str, int] = {}
            for a in alerts:
                r = self.handle(a, source=f"alertmanager@{host}")
                counts[r.disposition] = counts.get(r.disposition, 0) + 1
                if r.disposition == "started":
                    log.info("alert %s on %s: incident %s", a.labels.get("alertname"), host, r.incident_id)
            out[host] = counts
        return out
