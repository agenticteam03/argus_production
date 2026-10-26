"""ACR-0025 §3.1 (T-0046 L3): the scheduler records each declared container link's state when it changes.

On each reconcile tick, for every owner with a declared container dependency, the owner's probe samples since each
link's stored cursor are read from its own host's Prometheus at their source timestamps
(`MetricsPort.dependency_probe_history`, at most four hours back; ACR-0031), and each sample's state comes from
`application/links.py`, so the recorded history and the map never disagree. A `link_event` row is written only when a
link's state changes, and for a link with no cursor yet; each row is audited `link.changed`, and the row, its audit and
the cursor commit together. When a host's Prometheus cannot be read, that host's links are skipped and their cursors do
not move. A gap longer than the staleness limit between samples, or after the last one, is `unknown`, and an `unknown` link is read back at most the staleness limit. A host-kind
dependency (a filesystem, not a port) is never probed and never recorded.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Callable

from argus.application.links import LINK_WARNING_MS, link_state
from argus.domain.model import utcnow
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

    def owners(self) -> list:
        """The targets whose links are recorded: containers with a declared container dependency on their own host."""
        return [t for t in sorted(self.inventory.targets(), key=lambda x: str(x.ref))
                if t.ref.kind == "container" and any(recorded(t, d) for d in t.depends_on)]

    def run_once(self) -> str:
        now = self.now()
        skipped: set[str] = set()
        changed = 0
        max_staleness = timedelta(seconds=getattr(self.metrics, "max_staleness_s", 90))
        max_history = timedelta(seconds=getattr(self.metrics, "LINK_HISTORY_MAX_S", 4 * 60 * 60))
        ports = {str(t.ref): list(t.tcp_ports) for t in self.inventory.targets()}
        for owner in self.owners():
            deps = [d for d in owner.depends_on if recorded(owner, d)]
            if owner.ref.host in skipped or not deps:
                continue
            owner_ref = str(owner.ref)
            cursors = self.store.link_probe_cursors(owner_ref)
            # A link already `unknown` is read back no further than the staleness limit: a silent exporter, or a long
            # scheduler gap while it is silent, keeps the window short instead of growing to 4 h.
            starts = [max(c["at"], now - max_staleness) if c and c["state"] == "unknown" else
                      c["at"] if c else now - max_staleness
                      for c in (cursors.get(str(dep)) for dep in deps)]
            start = max(min(starts), now - max_history)
            try:
                history = self.metrics.dependency_probe_history(owner.ref, start, now) or {}
            except MetricsUnavailable:
                skipped.add(owner.ref.host)
                continue
            except (StaleMetrics, ValueError):
                history = {}

            for dep in deps:
                dep_ref = str(dep)
                cursor = cursors.get(dep_ref)
                last_at = cursor["at"] if cursor else None
                last_state = cursor["state"] if cursor else None
                if last_at is not None and last_at < start:
                    changed += self.store.record_link_probe(owner_ref, dep_ref, "unknown", None, None, start)
                    last_state, last_at = "unknown", start
                samples = sorted(history.get(dep.name, []), key=lambda sample: sample.at)

                if not cursor and not samples:
                    changed += self.store.record_link_probe(owner_ref, dep_ref, "unknown", None, None, now)
                    continue

                for sample in samples:
                    if sample.at > now or (last_at is not None and sample.at <= last_at):
                        continue
                    if last_at is not None and last_state != "unknown" and sample.at - last_at > max_staleness:
                        stale_at = last_at + max_staleness
                        changed += self.store.record_link_probe(owner_ref, dep_ref, "unknown", None, None, stale_at)
                        last_state, last_at = "unknown", stale_at
                    state, latency, reason = link_state(sample, owner.link_port(dep, ports.get(dep_ref)),
                                                        owner.link_warning_ms or LINK_WARNING_MS)
                    changed += self.store.record_link_probe(owner_ref, dep_ref, state, latency, reason, sample.at)
                    last_state, last_at = state, sample.at

                if last_at is not None and last_state != "unknown" and now - last_at > max_staleness:
                    stale_at = last_at + max_staleness
                    if stale_at <= now:
                        changed += self.store.record_link_probe(owner_ref, dep_ref, "unknown", None, None, stale_at)
                        last_state, last_at = "unknown", stale_at
        hosts = f"; skipped (Prometheus unreadable): {', '.join(sorted(skipped))}" if skipped else ""
        return f"{changed} link change(s) recorded{hosts}"
