"""ACR-0017: the metric window around an incident, for the UI's charts (`GET /api/v1/incidents/{id}/metrics`).

The browser chooses only the range (15m, 30m or 1h before the incident). The signals come from a fixed list per
incident class (`config/ui-incident-signals.yaml`), read through the MetricsPort on the incident's own host only.
At most ~130 points per series: the step grows for a long incident. A missing sample is `None` (a gap, never 0), and
a series that cannot be read is all gaps; the others still answer. One shared answer per (incident, range): 30 s
while the incident is open, 10 min once it is closed.

ACR-0021 (T-0045 B2) adds, all optional for a client: per series its `kind`, the `thresholds` of `config/signals.yaml`
scaled like the values and the detector's own line (`detector_threshold`); at the top the incident band
(`incident_from`, `incident_to`), the `events` (container restarts, OOM kills, alert fired / resolved) and a template
`summary` filled with numbers from the series (never a model call).
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from argus.domain.model import Incident, TargetRef
from argus.ports.ports import MetricsPort, MetricsUnavailable, StaleMetrics

RANGES = {"15m": 15, "30m": 30, "1h": 60}
MAX_POINTS = 130
MIN_STEP_S = 30
TAIL = timedelta(minutes=2)                 # the window ends a little after the incident closed
TOP_KEYS = {"default", "classes"}
SERIES_KEYS = {"signal", "title", "scope", "unit", "scale", "max", "fired", "kind"}
KINDS = ("memory", "restarts", "cpu", "latency", "health", "disk", "database", "network", "other")
SCOPES = {"target", "host"}


@dataclass(frozen=True)
class SeriesSpec:
    signal: str
    title: str
    scope: str = "target"
    unit: str = ""
    scale: float = 1.0
    max: float | None = None
    fired: bool = False
    kind: str = "other"


@dataclass(frozen=True)
class SignalList:
    default: tuple[SeriesSpec, ...] = ()
    by_class: dict[str, tuple[SeriesSpec, ...]] | None = None

    @classmethod
    def from_data(cls, data: Any, signals: set[str], classes: set[str]) -> "SignalList":
        """Validated like routing.yaml: an unknown key, signal, class or scope refuses the file (ValueError)."""
        data = data or {}
        if not isinstance(data, dict) or set(data) - TOP_KEYS:
            raise ValueError(f"ui-incident-signals: unknown key {sorted(set(data) - TOP_KEYS) if isinstance(data, dict) else data}")
        by_class = {}
        for name, entries in (data.get("classes") or {}).items():
            if name not in classes:
                raise ValueError(f"ui-incident-signals: unknown class {name!r}")
            by_class[name] = cls._series(entries, signals, name)
        return cls(default=cls._series(data.get("default") or [], signals, "default"), by_class=by_class)

    @staticmethod
    def _series(entries: Any, signals: set[str], where: str) -> tuple[SeriesSpec, ...]:
        if not isinstance(entries, list):
            raise ValueError(f"ui-incident-signals.{where}: a list of series")
        out = []
        for e in entries:
            if not isinstance(e, dict) or set(e) - SERIES_KEYS:
                raise ValueError(f"ui-incident-signals.{where}: unknown key in {e!r}")
            if e.get("signal") not in signals:
                raise ValueError(f"ui-incident-signals.{where}: unknown signal {e.get('signal')!r}")
            if not isinstance(e.get("title"), str) or not e["title"].strip():
                raise ValueError(f"ui-incident-signals.{where}.{e['signal']}: a title is required")
            if e.get("scope", "target") not in SCOPES:
                raise ValueError(f"ui-incident-signals.{where}.{e['signal']}: scope must be target or host")
            if not isinstance(e.get("fired", False), bool):
                raise ValueError(f"ui-incident-signals.{where}.{e['signal']}: fired must be true or false")
            if e.get("kind", "other") not in KINDS:
                raise ValueError(f"ui-incident-signals.{where}.{e['signal']}: kind must be one of {list(KINDS)}")
            for k in ("scale", "max"):
                if e.get(k) is not None and not isinstance(e[k], (int, float)):
                    raise ValueError(f"ui-incident-signals.{where}.{e['signal']}: {k} must be a number")
            out.append(SeriesSpec(signal=e["signal"], title=e["title"], scope=e.get("scope", "target"),
                                  unit=str(e.get("unit", "")), scale=float(e.get("scale", 1.0)),
                                  max=None if e.get("max") is None else float(e["max"]), fired=e.get("fired", False),
                                  kind=e.get("kind", "other")))
        return tuple(out)

    def for_class(self, name: str | None) -> tuple[SeriesSpec, ...]:
        return (self.by_class or {}).get(name, self.default) if name else self.default


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


class IncidentMetrics:
    def __init__(self, metrics: MetricsPort, signal_list: SignalList,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 clock: Callable[[], float] = time.monotonic, ttl_open_s: float = 30, ttl_closed_s: float = 600,
                 store=None, thresholds=None):
        """`store`: where the incident's alert occurrences are read (None = no alert events). `thresholds`: B1's
        `Thresholds` (None = no lines)."""
        self.metrics, self.signal_list, self.now, self.clock = metrics, signal_list, now, clock
        self.store, self.thresholds = store, thresholds
        self.ttl_open_s, self.ttl_closed_s = ttl_open_s, ttl_closed_s
        self._cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def window(self, inc: Incident, rng: str) -> dict:
        key = (inc.id, rng)
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > self.clock():
                return hit[1]
        answer = self._read(inc, rng)
        ttl = self.ttl_closed_s if inc.closed_at else self.ttl_open_s
        with self._lock:
            self._cache[key] = (self.clock() + ttl, answer)
            if len(self._cache) > 500:                     # a bound, not an LRU: drop the expired ones
                now = self.clock()
                self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        return answer

    def _read(self, inc: Incident, rng: str) -> dict:
        now = self.now()
        end = min(inc.closed_at + TAIL, now) if inc.closed_at else now
        end = datetime.fromtimestamp(math.floor(end.timestamp()), timezone.utc)      # whole seconds: readable times
        start = inc.opened_at - timedelta(minutes=RANGES[rng])
        minutes = max(1, math.ceil((end - start).total_seconds() / 60))
        step = max(MIN_STEP_S, math.ceil(minutes * 60 / MAX_POINTS))
        first = end.timestamp() - minutes * 60
        count = minutes * 60 // step + 1
        host = TargetRef(host=inc.target.host, kind="host", name=inc.target.host)
        memo: dict[tuple[str, str], dict[int, float]] = {}

        def slots_of(target: TargetRef, signal: str) -> dict[int, float]:
            """The signal's samples by slot (unscaled); this read is all gaps when it cannot be made."""
            if (str(target), signal) not in memo:
                try:
                    raw = self.metrics.range(target, signal, minutes, step, end=end)
                except (MetricsUnavailable, StaleMetrics, ValueError):
                    raw = []
                slots: dict[int, float] = {}
                for ts, value in raw:
                    i = round((ts - first) / step)
                    if 0 <= i < count and math.isfinite(value):
                        slots[i] = value
                memo[(str(target), signal)] = slots
            return memo[(str(target), signal)]

        series = []
        for spec in self.signal_list.for_class(inc.incident_class):
            slots = slots_of(host if spec.scope == "host" else inc.target, spec.signal)
            line = self.thresholds.get(spec.signal) if self.thresholds else None
            scaled = (None if line is None else
                      {"warning": round(line.warning * spec.scale, 6), "critical": round(line.critical * spec.scale, 6),
                       "direction": line.direction})
            series.append({"key": spec.signal, "title": spec.title, "unit": spec.unit, "max": spec.max,
                           "fired": spec.fired, "kind": spec.kind, "thresholds": scaled,
                           "detector_threshold": scaled["critical"] if scaled and spec.fired else None,
                           "points": [[_iso(first + i * step), None if i not in slots else round(slots[i] * spec.scale, 6)]
                                      for i in range(count)]})

        def at(i: int) -> str:
            return _iso(first + i * step)

        events = self._counter_events(inc, slots_of, at) + self._alert_events(inc, first, end.timestamp())
        events.sort(key=lambda e: e["at"])
        closed = inc.closed_at
        return {"incident_id": inc.id, "range": rng, "from": _iso(first), "to": _iso(end.timestamp()),
                "step_s": step, "incident_from": _iso(inc.opened_at.timestamp()),
                "incident_to": _iso(closed.timestamp()) if closed else None,
                "summary": summarize(inc.incident_class, series), "events": events, "series": series}

    @staticmethod
    def _counter_events(inc: Incident, slots_of, at) -> list[dict]:
        """Container restarts and OOM kills, where the counters step. A host has neither (no read is made)."""
        if inc.target.kind != "container":
            return []
        out = []
        restarts = slots_of(inc.target, "container_restart_count")
        order = sorted(restarts)
        for prev, cur in zip(order, order[1:]):
            if restarts[cur] > restarts[prev]:
                n = int(restarts[cur] - restarts[prev])
                out.append({"at": at(cur), "kind": "restart",
                            "label": "Container restarted" + (f" ({n} times)" if n > 1 else "")})
        oom = slots_of(inc.target, "oom_killed")
        order = sorted(oom)
        for prev, cur in zip(order, order[1:]):
            if oom[prev] < 1 <= oom[cur]:
                out.append({"at": at(cur), "kind": "oom_kill", "label": "Killed by the kernel (out of memory)"})
        return out

    def _alert_events(self, inc: Incident, start: float, stop: float) -> list[dict]:
        """The incident's alert occurrences (store) that fall inside the window."""
        if self.store is None:
            return []
        out = []
        for occ in self.store.alert_occurrences(inc.id):
            name = occ.get("alertname") or "alert"
            for when, kind, verb in ((occ.get("starts_at"), "alert_fired", "fired"),
                                     (occ.get("resolved_at"), "alert_resolved", "resolved")):
                if when is not None and start <= when.timestamp() <= stop:
                    out.append({"at": _iso(when.timestamp()), "kind": kind, "label": f"Alert {name} {verb}"})
        return out


# --- the summary: a template per class and per fired state, filled with numbers from the series -----------------------
# class -> (the series judged, "max" | "min", the limit (None = the series' detector line), fired text, calm text).
# `{x}` is a series' extreme with its unit; an unreadable one says "no data". No address, URL or model text.
SUMMARIES = {
    "container_restart_loop": ("restarts_10m", "max", None,
                               "{restarts_10m} restarts in 10 minutes; memory peaked at {container_memory_bytes}.",
                               "No restart loop in this window (at most {restarts_10m} restarts in 10 minutes); "
                               "memory peaked at {container_memory_bytes}."),
    "dependency_unavailable": ("dependency_probe_min", "min", 1,
                               "A declared dependency probe failed (lowest value {dependency_probe_min}, 1 = reachable).",
                               "Every declared dependency probe answered in this window."),
    "health_check_failed": ("health_unhealthy", "max", 1,
                            "The Docker health check reported unhealthy; restarts peaked at {restarts_10m} in 10 minutes.",
                            "The health check did not report unhealthy in this window."),
    "postgresql_connection_exhaustion": ("db_connection_usage", "max", None,
                                         "Connection slots in use reached {db_connection_usage}.",
                                         "Connection slots in use stayed at or below {db_connection_usage}."),
    "nginx_upstream_failure": ("http_gateway_error_ratio_5m", "max", None,
                               "Gateway errors reached {http_gateway_error_ratio_5m} of the probes.",
                               "Gateway errors stayed at or below {http_gateway_error_ratio_5m} of the probes."),
    "cpu_saturation": ("container_cpu_throttled_ratio_5m", "max", None,
                       "CPU periods throttled reached {container_cpu_throttled_ratio_5m}; quota used reached "
                       "{container_cpu_quota_used_ratio_5m}.",
                       "CPU periods throttled stayed at or below {container_cpu_throttled_ratio_5m}."),
    "disk_pressure": ("host_disk_used_ratio_5m", "max", None,
                      "A declared filesystem reached {host_disk_used_ratio_5m} used.",
                      "Disk used stayed at or below {host_disk_used_ratio_5m}."),
    "monitoring_blind_spot": ("scrape_targets_down", "max", 1,
                              "{scrape_targets_down} scrape target(s) down: the signals they feed are unknown.",
                              "Every scrape target was up in this window."),
}


class _Say(dict):
    def __missing__(self, key):
        return "no data"


def _shown(value: float, unit: str) -> str:
    return f"{value:g}" + (f" {unit}" if unit == "MiB" else unit if unit == "%" else "")


def summarize(cls: str | None, series: list[dict]) -> str:
    """One sentence about the window. Unknown is said as unknown, never as healthy."""
    if cls not in SUMMARIES:
        return "No incident class: host CPU and memory are shown for context."
    key, mode, limit, fired_text, calm_text = SUMMARIES[cls]
    say, judged = _Say(), None
    for s in series:
        values = [v for _, v in s["points"] if v is not None]
        if not values:
            continue
        top = min(values) if (s["key"] == key and mode == "min") else max(values)
        say[s["key"]] = _shown(top, s["unit"])
        if s["key"] == key:
            judged = (top, s["detector_threshold"])
    if judged is None:
        return "No data for the signal the detector reads in this window: its state is unknown."
    top, line = judged
    bound = limit if limit is not None else line
    fired = bound is not None and ((top < bound) if mode == "min" else (top >= bound))
    return (fired_text if fired else calm_text).format_map(say)
