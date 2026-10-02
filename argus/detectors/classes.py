"""Registered incident classes with pure detectors (v1.8 §1.3, §9; runbook library v1.1.0).

Detectors are pure functions of a MetricSnapshot. A missing value (None) is never treated as healthy
or as zero (G-007): it is reported as a finding and cannot trigger a class.
"""
from __future__ import annotations

from argus.domain.model import DetectorResult, IncidentClassSpec, MetricSnapshot


def _missing(snap: MetricSnapshot, *signals: str) -> list[str]:
    return [s for s in signals if snap.values.get(s) is None]


def container_restart_loop(snap: MetricSnapshot) -> DetectorResult:
    miss = _missing(snap, "restarts_10m")
    if miss:
        return DetectorResult(matched=False, findings=[f"signal missing (unknown, not healthy): {m}" for m in miss])
    restarts = snap.values["restarts_10m"]
    if restarts is not None and restarts >= 3:
        f = [f"{int(restarts)} restarts in the last 10 minutes"]
        oom = snap.values.get("oom_killed")
        code = snap.values.get("last_exit_code")
        f.append("last exit OOMKilled=" + ("unknown" if oom is None else str(bool(oom))))
        f.append("last exit code=" + ("unknown" if code is None else str(int(code))))
        if oom:   # wording that lets recall separate an OOM restart loop (RB-001) from a non-OOM crash (RB-008)
            f.append("killed by the kernel OOM killer at its container memory limit (out of memory)")
        elif oom is not None and code not in (None, 137):
            f.append("application crash: non-OOM exit")
        return DetectorResult(matched=True, findings=f)
    return DetectorResult(matched=False)


def dependency_unavailable(snap: MetricSnapshot) -> DetectorResult:
    v = snap.values.get("dependency_probe_min")
    if v is None:
        return DetectorResult(matched=False)          # target declares no dependency probes
    if v < 1:
        return DetectorResult(matched=True, findings=["at least one declared dependency probe is failing"])
    return DetectorResult(matched=False)


def health_check_failed(snap: MetricSnapshot) -> DetectorResult:
    v = snap.values.get("health_unhealthy")
    if v is None:
        return DetectorResult(matched=False)          # no health check configured / unknown
    if v >= 1:
        return DetectorResult(matched=True, findings=["Docker health check reports unhealthy"])
    return DetectorResult(matched=False)


# Priority order: the first matching class becomes the incident class; others become findings.
CLASSES: list[IncidentClassSpec] = [
    IncidentClassSpec(name="container_restart_loop", family="stability", target_kinds={"container"},
                      required_signals={"restarts_10m", "oom_killed", "last_exit_code"},
                      runbook_ids=["RB-001", "RB-008"], strategy="model_loop",
                      tool_tags={"stability", "memory", "logs", "container"}, detector=container_restart_loop),
    IncidentClassSpec(name="dependency_unavailable", family="dependency", target_kinds={"container"},
                      required_signals={"dependency_probe_min"}, runbook_ids=["RB-003"],
                      branch_runbook_ids=["RB-004", "RB-009"], strategy="model_loop",
                      tool_tags={"dependency", "network", "logs", "container", "availability"},
                      detector=dependency_unavailable),
    IncidentClassSpec(name="health_check_failed", family="availability", target_kinds={"container"},
                      required_signals={"health_unhealthy"}, runbook_ids=["RB-002"],
                      branch_runbook_ids=["RB-003"], strategy="model_loop",
                      tool_tags={"availability", "logs", "dependency", "network", "container"},
                      detector=health_check_failed),
]


def classes_for(kind: str) -> list[IncidentClassSpec]:
    return [c for c in CLASSES if kind in c.target_kinds]
