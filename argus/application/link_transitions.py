"""ACR-0025 §3.1 (T-0046 L3): the scheduler records each declared container link's state when it changes.

On each reconcile tick, for every owner with a declared container dependency, the owner's probes are read from its own
host's Prometheus (`MetricsPort.dependency_probes`, the read the topology does) and each link's state comes from
`application/links.py`, so the recorded history and the map never disagree. A `link_event` row is written only when a
link's state changes, and once at startup (this process has seen nothing yet); each row is audited `link.changed`.
When a host's Prometheus cannot be read, that host's links are skipped for the tick: no burst of `unknown` and then
of recoveries. A sample read but stale is `unknown`. A host-kind dependency (a filesystem, not a port) is never probed
and never recorded.
"""
from __future__ import annotations

import uuid
from typing import Callable

from argus.application.links import LINK_WARNING_MS, link_state
from argus.domain.model import AuditRecord, utcnow
from argus.ports.ports import MetricsUnavailable, StaleMetrics


class LinkTransitions:
    def __init__(self, store, inventory, metrics, now: Callable = utcnow):
        self.store, self.inventory, self.metrics, self.now = store, inventory, metrics, now
        self._last: dict[tuple[str, str], str] = {}     # (owner, dependency) -> the state last recorded

    def owners(self) -> list:
        """The targets whose links are recorded: containers with a declared container dependency on their own host."""
        return [t for t in sorted(self.inventory.targets(), key=lambda x: str(x.ref))
                if t.ref.kind == "container" and any(self._recorded(t, d) for d in t.depends_on)]

    @staticmethod
    def _recorded(owner, dep) -> bool:
        return dep.kind == "container" and dep.host == owner.ref.host

    def run_once(self) -> str:
        ports = {str(t.ref): list(t.tcp_ports) for t in self.inventory.targets()}
        skipped: set[str] = set()
        changed = 0
        for t in self.owners():
            if t.ref.host in skipped:
                continue
            try:
                probes = self.metrics.dependency_probes(t.ref) or {}
            except MetricsUnavailable:
                skipped.add(t.ref.host)              # this host's Prometheus is unreadable: record nothing this tick
                continue
            except (StaleMetrics, ValueError):
                probes = {}                          # read, but nothing fresh: every link of the owner is `unknown`
            warn = t.link_warning_ms or LINK_WARNING_MS
            for dep in t.depends_on:
                if not self._recorded(t, dep):
                    continue
                state, latency, why = link_state(probes.get(dep.name), t.link_port(dep, ports.get(str(dep))), warn)
                key = (str(t.ref), str(dep))
                previous = self._last.get(key)
                if previous == state:
                    continue
                reason = (why or "not reachable") if state == "broken" else None     # as the map labels it
                at = self.now()
                self.store.add_link_event(key[0], key[1], state, latency, reason, at)
                self.store.append(AuditRecord(
                    audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=at, category="incident",
                    event="link.changed", actor="scheduler",
                    detail={"owner": key[0], "dependency": key[1], "from": previous, "to": state,
                            "latency_ms": latency, "reason": reason}))
                self._last[key] = state
                changed += 1
        hosts = f"; skipped (Prometheus unreadable): {', '.join(sorted(skipped))}" if skipped else ""
        return f"{changed} link change(s) recorded{hosts}"
