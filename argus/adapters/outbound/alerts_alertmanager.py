"""AlertSourcePort over the Alertmanager API v2 (ARCHITECTURE §7.3, §8.1; ACR-0003, T-0022).

One Argus-owned Alertmanager per host, URL from the inventory (`hosts.<name>.alertmanager`). `firing_alerts` reads
the active alerts that are neither silenced nor inhibited (what intake submits); `active_alerts` reads every active
alert, silenced and inhibited included, so that only an alert that really stopped counts as resolved (ACR-0005). An
alert is returned only when its `argus_host` label is the host
asked: another host's alert is dropped and logged, never reassigned (no cross-host fallback, §3.2). Argus's own security
alerts (`argus_security="true"`, ACR-0018 §18) go to the team, never to intake: they are skipped silently.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from argus.domain.model import AlertNotification
from argus.ports.ports import AlertsUnavailable

log = logging.getLogger("argus.alerts")


def _ts(value: str | None) -> datetime | None:
    if not value or value.startswith("0001-"):           # Alertmanager's zero time = unset
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class AlertmanagerSource:
    def __init__(self, urls: dict[str, str], client: httpx.Client | None = None, timeout_s: float = 8.0):
        self.urls = {h: u.rstrip("/") for h, u in urls.items() if u}
        self.client = client or httpx.Client(timeout=timeout_s)

    def firing_alerts(self, host: str) -> list[AlertNotification]:
        return self._read(host, {"active": "true", "silenced": "false", "inhibited": "false"})

    def active_alerts(self, host: str) -> list[AlertNotification]:
        return self._read(host, {"active": "true", "silenced": "true", "inhibited": "true", "unprocessed": "true"})

    def _read(self, host: str, params: dict[str, str]) -> list[AlertNotification]:
        base = self.urls.get(host)
        if not base:
            raise AlertsUnavailable(f"no alertmanager for host {host} in the inventory")
        try:
            r = self.client.get(f"{base}/api/v2/alerts", params=params)
            r.raise_for_status()
            items = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise AlertsUnavailable(f"alertmanager of {host}: {type(e).__name__}") from e
        out = []
        for it in items:
            labels = {str(k): str(v) for k, v in (it.get("labels") or {}).items()}
            if labels.get("argus_security") == "true":
                continue
            if labels.get("argus_host") != host:
                log.warning("dropped alert %s from %s's Alertmanager: argus_host=%r", labels.get("alertname"), host,
                            labels.get("argus_host"))
                continue
            starts = _ts(it.get("startsAt"))
            if starts is None or not it.get("fingerprint"):
                continue
            out.append(AlertNotification(fingerprint=str(it["fingerprint"]), status="firing", starts_at=starts,
                                         ends_at=_ts(it.get("endsAt")), updated_at=_ts(it.get("updatedAt")),
                                         labels=labels,
                                         annotations={str(k): str(v)
                                                      for k, v in (it.get("annotations") or {}).items()}))
        return out
