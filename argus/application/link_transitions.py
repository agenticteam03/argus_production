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


def recorded(owner, dep) -> bool:
    """A link whose state is recorded and read: a container dependency on the owner's own host."""
    return dep.kind == "container" and dep.host == owner.ref.host


def read_links(inventory, metrics, owners) -> tuple[list[tuple[str, str, str, float | None, str | None]], set[str]]:
    """The current state of every recorded link of `owners`: ([(owner, dependency, state, latency_ms, reason)], the
    hosts skipped because their Prometheus cannot be read). One read per owner, on its own host; `links.py`'s rules;
    a broken link's reason as the map labels it. Used by the recorder and by `network.link_states` (T-0046 L4)."""
    ports = {str(t.ref): list(t.tcp_ports) for t in inventory.targets()}
    skipped: set[str] = set()
    out = []
    for t in owners:
        if t.ref.host in skipped:
            continue
        try:
            probes = metrics.dependency_probes(t.ref) or {}
        except MetricsUnavailable:
            skipped.add(t.ref.host)                  # this host's Prometheus is unreadable: nothing from it this time
            continue
        except (StaleMetrics, ValueError):
            probes = {}                              # read, but nothing fresh: every link of the owner is `unknown`
        warn = t.link_warning_ms or LINK_WARNING_MS
        for dep in t.depends_on:
            if not recorded(t, dep):
                continue
            state, latency, why = link_state(probes.get(dep.name), t.link_port(dep, ports.get(str(dep))), warn)
            out.append((str(t.ref), str(dep), state, latency, (why or "not reachable") if state == "broken" else None))
    return out, skipped


class LinkTransitions:
    def __init__(self, store, inventory, metrics, now: Callable = utcnow):
        self.store, self.inventory, self.metrics, self.now = store, inventory, metrics, now
        self._last: dict[tuple[str, str], str] = {}     # (owner, dependency) -> the state last recorded

    def owners(self) -> list:
        """The targets whose links are recorded: containers with a declared container dependency on their own host."""
        return [t for t in sorted(self.inventory.targets(), key=lambda x: str(x.ref))
                if t.ref.kind == "container" and any(recorded(t, d) for d in t.depends_on)]

    def run_once(self) -> str:
        links, skipped = read_links(self.inventory, self.metrics, self.owners())
        changed = 0
        for owner, dep, state, latency, reason in links:
            key = (owner, dep)
            previous = self._last.get(key)
            if previous == state:
                continue
            at = self.now()
            self.store.add_link_event(owner, dep, state, latency, reason, at)
            self.store.append(AuditRecord(
                audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=at, category="incident",
                event="link.changed", actor="scheduler",
                detail={"owner": owner, "dependency": dep, "from": previous, "to": state, "latency_ms": latency,
                        "reason": reason}))
            self._last[key] = state
            changed += 1
        hosts = f"; skipped (Prometheus unreadable): {', '.join(sorted(skipped))}" if skipped else ""
        return f"{changed} link change(s) recorded{hosts}"
