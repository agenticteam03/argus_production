"""Alert correlation (ARCHITECTURE §6.4; OP-011).

An alert joins the target's open incident (queued or running) whose last evidence is within `CORRELATION_WINDOW`;
otherwise (ACR-0004) the target's latest concluded incident (closed or escalated) if the alert started at or before
that incident closed (the same episode, pulled after the diagnosis) and it closed within the window. Either way it
must pass the compatibility test: the class's detectors, run on a fresh snapshot of the target, give the incident's
class (or, for an incident not yet detected, a class at all: its own detection reads the same target), and the
alert's labels name no other container or dependency than the incident's. A test that cannot run (stale or
unavailable metrics) never merges: independent failures stay apart. Joining a concluded incident starts no run and
does not reopen it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from argus.detectors.classes import classes_for
from argus.domain.model import Incident, TargetRef
from argus.ports.ports import MetricsUnavailable, StaleMetrics

CORRELATION_WINDOW = timedelta(minutes=30)


def detected_class(metrics, target: TargetRef) -> str | None:
    """The class the detect node would choose for `target` now (the first registered class that matches)."""
    classes = classes_for(target.kind)
    if not classes:
        return None
    snap = metrics.snapshot(target, set().union(*(c.required_signals for c in classes)))
    return next((c.name for c in classes if c.detector(snap).matched), None)


@dataclass(frozen=True)
class Correlation:
    incident: Incident | None           # the open incident to attach to; None = open a new incident
    incident_class: str | None
    reason: str


class Correlator:
    def __init__(self, store, metrics, window: timedelta = CORRELATION_WINDOW):
        self.store, self.metrics, self.window = store, metrics, window

    def _labels_compatible(self, inc: Incident, labels: dict[str, str]) -> str | None:
        named = {labels.get(k) for k in ("container", "owner")} - {None}
        if inc.target.kind == "container" and named - {inc.target.name}:
            return f"the alert names another container: {sorted(named)}"
        dep = labels.get("dependency")
        known = {o["labels"].get("dependency") for o in self.store.alert_occurrences(inc.id)} - {None}
        if dep and known and dep not in known:
            return f"the alert names another dependency ({dep}, the incident has {sorted(known)})"
        return None

    def _candidate(self, target: TargetRef, starts_at: datetime, now: datetime) -> tuple[Incident | None, str]:
        inc = self.store.active_incident(target)
        if inc is not None:
            _, last = self.store.evidence_state(inc.id)
            if now - (last or inc.opened_at) > self.window:
                return None, f"{inc.id}: last evidence outside the correlation window"
            return inc, "open"
        inc = self.store.latest_concluded_incident(target)                # ACR-0004: the same episode
        if inc is None or inc.closed_at is None or inc.incident_class is None:
            return None, "no open incident on the target"
        if starts_at > inc.closed_at:
            return None, f"{inc.id} closed before the alert started (a recurrence)"
        if now - inc.closed_at > self.window:
            return None, f"{inc.id}: closed outside the correlation window"
        return inc, "concluded, same episode"

    def match(self, target: TargetRef, labels: dict[str, str], starts_at: datetime, now: datetime) -> Correlation:
        inc, why = self._candidate(target, starts_at, now)
        if inc is None:
            return Correlation(None, None, why)
        other = self._labels_compatible(inc, labels)
        if other:
            return Correlation(None, None, f"{inc.id}: {other}")
        try:
            cls = detected_class(self.metrics, target)
        except (StaleMetrics, MetricsUnavailable) as e:
            return Correlation(None, None, f"{inc.id}: compatibility test not run ({e})")
        if cls is None:
            return Correlation(None, None, f"{inc.id}: a fresh detection matches no class")
        if inc.incident_class not in (None, cls):
            return Correlation(None, cls, f"{inc.id}: class {inc.incident_class}, the fresh detection gives {cls}")
        return Correlation(inc, cls, f"same target and class {cls} ({why})")
