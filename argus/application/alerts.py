"""Alert intake (ARCHITECTURE §6.1 A and D, §6.6, §7.3; ACR-0002, T-0022).

`HandleAlertNotification` turns one `AlertNotification` into durable intake. The push webhook and the pull
reconciliation both call it, so one alert gives one incident whichever way it arrived: the identity is
`fingerprint + startsAt` (§6.6). `ReconcileFiringAlerts` reads each host's Alertmanager through `AlertSourcePort`
and submits every firing alert; a host that cannot be read is reported and the others go on.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from argus.domain.model import (AlertNotification, AuditRecord, Incident, RequestKind, TargetRef, TriggerKind,
                                utcnow)
from argus.ports.ports import AlertSourcePort, AlertsUnavailable

log = logging.getLogger("argus.alerts")


@dataclass(frozen=True)
class IntakeResult:
    disposition: Literal["started", "duplicate", "ignored", "refused"]
    incident_id: str | None = None
    detail: str = ""


def alert_identity(a: AlertNotification) -> str:
    """§6.6: the same string for a pushed and a pulled copy of one alert firing."""
    return f"alert:{a.fingerprint}:{a.starts_at.isoformat()}"


class HandleAlertNotification:
    def __init__(self, store, inventory):
        self.store, self.inventory = store, inventory

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
        reason = f"alert {a.labels.get('alertname', '?')}: {a.annotations.get('summary', '')}"
        inc = Incident(id=f"inc_{uuid.uuid4().hex[:12]}", target=target, trigger_kind=TriggerKind.alert,
                       request_kind=RequestKind.report, reason=reason[:2000], principal=source, trigger_id=key,
                       opened_at=utcnow())
        inc, duplicate = self.store.create_incident(inc, key)
        return IntakeResult("duplicate" if duplicate else "started", inc.id)


class ReconcileFiringAlerts:
    """§7.3: the primary trigger in a pull profile (ACR-0002), the outage backup in a push profile."""

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
