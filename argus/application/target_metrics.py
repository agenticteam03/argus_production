"""ACR-0021 (T-0045 B6): one inventory target's recent signals, for the UI's drawer (`GET /api/v1/target-metrics`).

The browser names the target and a range (15m or 1h); the server picks the series: CPU quota used and memory for a
container; CPU, memory used and disk used for a host (another kind has no named series yet). They are read through the
MetricsPort on the target's own host only, at most ~130 points per series, with the UI's warning and critical lines
(`config/signals.yaml` `thresholds:`). A missing sample is `None` (a gap, never 0), and a series that cannot be read is
all gaps; the others still answer. One shared answer per (target, range) for 30 s.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from argus.application.incident_metrics import MAX_POINTS, MIN_STEP_S, _iso
from argus.domain.model import TargetRef
from argus.ports.ports import MetricsPort, MetricsUnavailable, StaleMetrics

RANGES = {"15m": 15, "1h": 60}


@dataclass(frozen=True)
class Series:
    key: str                            # the name in the answer
    signal: str                         # the named signal read (config/signals.yaml)
    kind: str
    title: str
    unit: str
    max: float | None = None
    used: bool = False                  # the signal is an available ratio: answer 1 - value, with the lines flipped


SERIES = {
    "container": (Series("container_cpu_quota_used_ratio_5m", "container_cpu_quota_used_ratio_5m", "cpu",
                         "CPU quota used", "ratio", 1.0),
                  Series("container_memory_bytes", "container_memory_bytes", "memory", "Memory", "bytes")),
    "host": (Series("host_cpu_busy_ratio", "host_cpu_busy_ratio", "cpu", "CPU busy", "ratio", 1.0),
             Series("host_memory_used_ratio", "host_memory_available_ratio", "memory", "Memory used", "ratio", 1.0,
                    used=True),
             Series("host_disk_used_ratio", "host_disk_used_ratio", "disk", "Disk used", "ratio", 1.0)),
}


class TargetMetrics:
    def __init__(self, metrics: MetricsPort, thresholds=None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 clock: Callable[[], float] = time.monotonic, ttl_s: float = 30):
        self.metrics, self.thresholds, self.now, self.clock, self.ttl_s = metrics, thresholds, now, clock, ttl_s
        self._cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def window(self, target: TargetRef, rng: str) -> dict:
        key = (str(target), rng)
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > self.clock():
                return hit[1]
        answer = self._read(target, rng)
        with self._lock:
            self._cache[key] = (self.clock() + self.ttl_s, answer)
            if len(self._cache) > 500:                     # a bound, not an LRU: drop the expired ones
                now = self.clock()
                self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        return answer

    def _lines(self, spec: Series) -> dict | None:
        t = self.thresholds.get(spec.signal) if self.thresholds else None
        return (t.complement() if spec.used else t).as_dict() if t else None

    def _read(self, target: TargetRef, rng: str) -> dict:
        end = math.floor(self.now().timestamp())           # whole seconds: readable times
        minutes = RANGES[rng]
        step = max(MIN_STEP_S, math.ceil(minutes * 60 / MAX_POINTS))
        first = end - minutes * 60
        count = minutes * 60 // step + 1
        series = []
        for spec in SERIES.get(target.kind, ()):
            try:
                raw = self.metrics.range(target, spec.signal, minutes, step,
                                         end=datetime.fromtimestamp(end, timezone.utc))
            except (MetricsUnavailable, StaleMetrics, ValueError):
                raw = []                                     # this series is all gaps; the others still answer
            slots: dict[int, float] = {}
            for ts, value in raw:
                i = round((ts - first) / step)
                if 0 <= i < count and math.isfinite(value):
                    slots[i] = round(1 - value if spec.used else value, 6)
            series.append({"key": spec.key, "kind": spec.kind, "title": spec.title, "unit": spec.unit,
                           "max": spec.max, "thresholds": self._lines(spec),
                           "points": [[_iso(first + i * step), slots.get(i)] for i in range(count)]})
        return {"target": str(target), "range": rng, "from": _iso(first), "to": _iso(end), "step_s": step,
                "series": series}
