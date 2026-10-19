"""ACR-0021 (T-0045 B6): the dashboard in one answer (`GET /api/v1/overview`).

Built only from what Argus already holds: the stored incidents (the newest `limit`), the shared topology snapshot (B3)
and the shared host-metrics snapshot (B1). No new host read and no executor call. `status` is the worst severity among
the open incidents (`ok` when none is open); an open incident whose class is not known yet is `info`. One shared answer
for 15 s.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable

from argus.application.incident_view import CLASS_TEXT, _severity, _summary
from argus.detectors.classes import CLASSES
from argus.domain.model import IncidentStatus

SEVERITIES = ("critical", "warning", "info")
HEALTH = ("healthy", "degraded", "failed", "unknown", "idle")
LATEST = 5
FINAL = (IncidentStatus.closed, IncidentStatus.escalated)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class Overview:
    def __init__(self, store, topology, host_rows: Callable[[], list[dict]], classes=CLASSES, limit: int = 200,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 clock: Callable[[], float] = time.monotonic, ttl_s: float = 15):
        self.store, self.topology, self.host_rows, self.limit = store, topology, host_rows, limit
        self.specs = {c.name: c for c in classes}
        self.now, self.clock, self.ttl_s = now, clock, ttl_s
        self._cached: tuple[float, dict] | None = None
        self._lock = threading.Lock()

    def view(self) -> dict:
        with self._lock:
            if self._cached and self._cached[0] > self.clock():
                return self._cached[1]
        answer = self._build()
        with self._lock:
            self._cached = (self.clock() + self.ttl_s, answer)
        return answer

    def _build(self) -> dict:
        incidents = self.store.list_incidents(self.limit)                  # newest first
        open_rows, counts = [], {s: 0 for s in SEVERITIES}
        for inc in incidents:
            if inc.status in FINAL:
                continue
            spec = self.specs.get(inc.incident_class or "")
            severity = _severity(inc, spec) or "info"
            severity = severity if severity in counts else "info"         # an open "ok" (no incident) is not a problem
            counts[severity] += 1
            open_rows.append({"id": inc.id, "target": str(inc.target), "host": inc.target.host, "severity": severity,
                              "kind": CLASS_TEXT.get(spec.name if spec else "", (None, None))[1],
                              "summary": _summary(inc, spec), "opened_at": _iso(inc.opened_at),
                              "next_action": None})                       # B4's next_actions are empty until runbooks say
        closed = [i.closed_at for i in incidents if i.closed_at]
        topo = self.topology.view()
        fleet = {h: 0 for h in HEALTH}
        for node in topo.get("nodes", []):
            fleet[node.get("health") if node.get("health") in fleet else "unknown"] += 1
        deps = [e for e in topo.get("edges", []) if e.get("kind") == "dependency"]
        status = next((s for s in SEVERITIES if counts[s]), "ok")
        return {"observed_at": _iso(self.now()), "status": status, "open_incidents": counts,
                "latest_open": open_rows[:LATEST], "hosts": self.host_rows(), "fleet": fleet,
                "links": {"ok": sum(1 for e in deps if e.get("state") == "ok"), "total": len(deps)},
                "last_closed_at": _iso(max(closed)) if closed else None}
