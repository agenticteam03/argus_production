"""ACR-0017: the metric window around an incident, for the UI's charts (`GET /api/v1/incidents/{id}/metrics`).

The browser chooses only the range (15m, 30m or 1h before the incident). The signals come from a fixed list per
incident class (`config/ui-incident-signals.yaml`), read through the MetricsPort on the incident's own host only.
At most ~130 points per series: the step grows for a long incident. A missing sample is `None` (a gap, never 0), and
a series that cannot be read is all gaps; the others still answer. One shared answer per (incident, range): 30 s
while the incident is open, 10 min once it is closed.
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
SERIES_KEYS = {"signal", "title", "scope", "unit", "scale", "max", "fired"}
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
            for k in ("scale", "max"):
                if e.get(k) is not None and not isinstance(e[k], (int, float)):
                    raise ValueError(f"ui-incident-signals.{where}.{e['signal']}: {k} must be a number")
            out.append(SeriesSpec(signal=e["signal"], title=e["title"], scope=e.get("scope", "target"),
                                  unit=str(e.get("unit", "")), scale=float(e.get("scale", 1.0)),
                                  max=None if e.get("max") is None else float(e["max"]), fired=e.get("fired", False)))
        return tuple(out)

    def for_class(self, name: str | None) -> tuple[SeriesSpec, ...]:
        return (self.by_class or {}).get(name, self.default) if name else self.default


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


class IncidentMetrics:
    def __init__(self, metrics: MetricsPort, signal_list: SignalList,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 clock: Callable[[], float] = time.monotonic, ttl_open_s: float = 30, ttl_closed_s: float = 600):
        self.metrics, self.signal_list, self.now, self.clock = metrics, signal_list, now, clock
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
        series = []
        for spec in self.signal_list.for_class(inc.incident_class):
            target = host if spec.scope == "host" else inc.target
            try:
                raw = self.metrics.range(target, spec.signal, minutes, step, end=end)
            except (MetricsUnavailable, StaleMetrics, ValueError):
                raw = []                                     # this series is all gaps; the others still answer
            slots: dict[int, float] = {}
            for ts, value in raw:
                i = round((ts - first) / step)
                if 0 <= i < count and math.isfinite(value):
                    slots[i] = round(value * spec.scale, 6)
            series.append({"key": spec.signal, "title": spec.title, "unit": spec.unit, "max": spec.max,
                           "fired": spec.fired,
                           "points": [[_iso(first + i * step), slots.get(i)] for i in range(count)]})
        return {"incident_id": inc.id, "range": rng, "from": _iso(first), "to": _iso(end.timestamp()),
                "step_s": step, "series": series}
