"""ACR-0025: the state of one declared dependency link from the exporter's probe sample, in one place.

The topology (`GET /api/v1/topology`) reads it at request time; the scheduler (T-0046 L3) records its transitions.
Both use these rules, so the map and the recorded history never disagree on what `ok`, `slow` and `broken` mean.
A link Argus cannot judge is `unknown`, never ok.
"""
from __future__ import annotations

from argus.ports.ports import ProbeSample

LINK_WARNING_MS = 100.0                    # a dependency answer slower than this is `slow` (inventory: link_warning_ms)
# T-0045 B8: the exporter's failure kind of a broken link, in plain words ("other" and none stay "not reachable")
LINK_REASONS = {"refused": "connection refused", "timeout": "timeout", "dns": "name not resolved",
                "protocol": "no protocol answer"}


def link_state(sample: ProbeSample | None, port: int | None,
               warn_ms: float = LINK_WARNING_MS) -> tuple[str, float | None, str | None]:
    """(state, latency in ms, B8 reason) of one link. `unknown` without a sample, a success value or a port (a host
    dependency has no port and is never probed); the reason is set only for a known failure kind of a broken link."""
    if sample is None:
        return "unknown", None, None
    latency = None if sample.duration_s is None else round(sample.duration_s * 1000, 3)
    if sample.success is None or port is None:
        return "unknown", latency, None
    if sample.success < 1:
        return "broken", latency, LINK_REASONS.get(sample.error_kind or "")
    return ("slow" if latency is not None and latency > warn_ms else "ok"), latency, None
