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


def postgresql_connection_exhaustion(snap: MetricSnapshot) -> DetectorResult:
    """RB-004: ordinary-slot usage at or above 90 % for 5 minutes (the signal is the 5-minute minimum)."""
    up = snap.values.get("db_up")
    if up is None:
        return DetectorResult(matched=False)          # no database metrics for this target (not a database)
    if up < 1:
        return DetectorResult(matched=False, findings=["database not readable by the db-probe (unknown, not healthy)"])
    usage = snap.values.get("db_connection_usage")
    if usage is None:
        return DetectorResult(matched=False, findings=["signal missing (unknown, not healthy): db_connection_usage"])
    if usage >= 0.9:
        return DetectorResult(matched=True, findings=[
            f"{round(usage * 100)}% of the usable connection slots in use for at least 5 minutes",
            "connection capacity is almost exhausted: new ordinary clients may be rejected (SQLSTATE 53300)"])
    return DetectorResult(matched=False)


def disk_pressure(snap: MetricSnapshot) -> DetectorResult:
    """RB-005: a declared mount at or above 90 % used for 5 minutes (the signal is the worst mount's 5-minute
    minimum); the time to full comes from the 15-minute fill rate and is absent when nothing grows."""
    used = snap.values.get("host_disk_used_ratio_5m")
    if used is None:
        return DetectorResult(matched=False, findings=["signal missing (unknown, not healthy): host_disk_used_ratio_5m"])
    if used < 0.9:
        return DetectorResult(matched=False)
    f = [f"a declared filesystem of the host is {round(used * 100)}% used for at least 5 minutes"]
    hours = snap.values.get("host_disk_hours_to_full")
    if hours is None:
        f.append("its free space is not growing smaller now (no time-to-full estimate)")
    elif hours < 2:
        f.append(f"at the last 15 minutes' fill rate it is full in about {max(1, round(hours * 60))} min")
    else:
        f.append(f"at the last 15 minutes' fill rate it is full in about {round(hours, 1)} h")
    return DetectorResult(matched=True, findings=f)


def monitoring_blind_spot(snap: MetricSnapshot) -> DetectorResult:
    """RB-014 (T-0027): a scrape target of the host's Prometheus is down, so the signals it feeds are empty. That is
    a loss of visibility, never a healthy host (G-007). The gate exporter's own outage ends earlier, as
    `undiagnosable`."""
    down = snap.values.get("scrape_targets_down")
    if down is None:
        return DetectorResult(matched=False, findings=["signal missing (unknown, not healthy): scrape_targets_down"])
    if down < 1:
        return DetectorResult(matched=False)
    n = int(down)
    return DetectorResult(matched=True, findings=[
        f"{n} scrape target{'s' if n != 1 else ''} down on the host's Prometheus: the signals they feed are unknown",
        "monitoring blind spot (RB-014): no diagnosis of the host's state is claimed from missing telemetry"])


def cpu_saturation(snap: MetricSnapshot) -> DetectorResult:
    """RB-006, the container trigger (T-0028): for 5 minutes, half or more of the container's CPU periods throttled at
    its quota AND 80 % or more of the quota used (both signals are 5-minute minimums). The throttled share alone counts
    only the periods the container ran in: a bursty container far below its quota is not saturated (calibrated on
    vm-166). The busy-host trigger is separate and not registered yet."""
    miss = _missing(snap, "container_cpu_throttled_ratio_5m", "container_cpu_quota_used_ratio_5m")
    if miss:
        return DetectorResult(matched=False, findings=[f"signal missing (unknown, not healthy): {m}" for m in miss])
    ratio, used = snap.values["container_cpu_throttled_ratio_5m"], snap.values["container_cpu_quota_used_ratio_5m"]
    if ratio < 0.5 or used < 0.8:
        return DetectorResult(matched=False)
    return DetectorResult(matched=True, findings=[
        f"{round(ratio * 100)}% of its CPU periods throttled at its CPU quota for at least 5 minutes",
        f"it uses {round(used * 100)}% of its CPU quota: CPU saturation of the container (RB-006), its work needs "
        "more CPU than its limit gives"])


def nginx_upstream_failure(snap: MetricSnapshot) -> DetectorResult:
    """RB-015 (T-0029): half or more of the synthetic probes through the proxy's endpoint got 502/504 over 5 minutes:
    the proxy could not get an answer from its upstream. An app's own 5xx (for example 503) is not counted."""
    share = snap.values.get("http_gateway_error_ratio_5m")
    if share is None:
        return DetectorResult(matched=False, findings=["signal missing (unknown, not healthy): http_gateway_error_ratio_5m"])
    if share < 0.5:
        return DetectorResult(matched=False)
    return DetectorResult(matched=True, findings=[
        f"{round(share * 100)}% of the probes through its endpoint got a gateway error (502/504) in the last 5 minutes",
        "the proxy cannot get an answer from its upstream in time (RB-015): look at the upstream it depends on"])


# Priority order: the first matching class becomes the incident class; others become findings.
CLASSES: list[IncidentClassSpec] = [
    IncidentClassSpec(name="container_restart_loop", family="stability", target_kinds={"container"},
                      required_signals={"restarts_10m", "oom_killed", "last_exit_code"},
                      runbook_ids=["RB-001", "RB-008"], strategy="model_loop",
                      tool_tags={"stability", "memory", "logs", "container"}, detector=container_restart_loop),
    IncidentClassSpec(name="dependency_unavailable", family="dependency", target_kinds={"container"},
                      required_signals={"dependency_probe_min"}, runbook_ids=["RB-003"],
                      branch_runbook_ids=["RB-004", "RB-009"], strategy="model_loop",
                      tool_tags={"dependency", "network", "logs", "container", "availability", "knowledge"},
                      detector=dependency_unavailable),
    IncidentClassSpec(name="health_check_failed", family="availability", target_kinds={"container"},
                      required_signals={"health_unhealthy"}, runbook_ids=["RB-002"],
                      branch_runbook_ids=["RB-003"], strategy="model_loop",
                      tool_tags={"availability", "logs", "dependency", "network", "container", "knowledge"},
                      detector=health_check_failed),
    IncidentClassSpec(name="postgresql_connection_exhaustion", family="database", target_kinds={"container"},
                      required_signals={"db_connection_usage", "db_up"}, runbook_ids=["RB-004"],
                      branch_runbook_ids=["RB-013"], strategy="model_loop",
                      tool_tags={"database", "logs", "container", "dependency", "knowledge"},
                      detector=postgresql_connection_exhaustion),
    # T-0027: a host that lost part of its telemetry is a blind spot before it is anything else (unknown first).
    IncidentClassSpec(name="monitoring_blind_spot", family="platform", target_kinds={"host"},
                      required_signals={"scrape_targets_down"}, runbook_ids=["RB-014"], strategy="evidence_pack",
                      tool_tags={"host", "container", "logs"}, detector=monitoring_blind_spot),
    IncidentClassSpec(name="cpu_saturation", family="saturation", target_kinds={"container"},
                      required_signals={"container_cpu_throttled_ratio_5m", "container_cpu_quota_used_ratio_5m"},
                      runbook_ids=["RB-006"],
                      strategy="model_loop", tool_tags={"cpu", "container", "logs", "host", "knowledge"},
                      detector=cpu_saturation),
    IncidentClassSpec(name="nginx_upstream_failure", family="availability", target_kinds={"container"},
                      required_signals={"http_gateway_error_ratio_5m"}, runbook_ids=["RB-015"],
                      branch_runbook_ids=["RB-002", "RB-003"], strategy="plan_then_reason",
                      tool_tags={"availability", "network", "dependency", "logs", "container", "knowledge"},
                      detector=nginx_upstream_failure),
    IncidentClassSpec(name="disk_pressure", family="saturation", target_kinds={"host"},
                      required_signals={"host_disk_used_ratio_5m", "host_disk_hours_to_full"}, runbook_ids=["RB-005"],
                      branch_runbook_ids=["RB-019"], strategy="model_loop",
                      tool_tags={"host", "disk", "logs", "container", "knowledge"}, detector=disk_pressure),
]


def classes_for(kind: str) -> list[IncidentClassSpec]:
    return [c for c in CLASSES if kind in c.target_kinds]
