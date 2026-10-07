"""Level 1 (+ first Level 2) capabilities of v1.8 §12.2 for the lab.

Implementations only build a request for their executor and summarise the answer. They never decide
authorization, read configuration or write audit (v1.8 §12.3).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from argus.capabilities.spec import CapabilityResult, CapabilitySpec, ExecutorError
from argus.domain.model import TargetInfo, TargetRef


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(_Args):
    pass


class LogsArgs(_Args):
    tail: int = Field(50, ge=1, le=200, description="number of most recent log lines")


class EventsArgs(_Args):
    minutes: int = Field(30, ge=1, le=120, description="lookback window in minutes")


class DiskArgs(_Args):
    mount: str = Field("/", description="an allowlisted mount point of the host")


class PortArgs(_Args):
    port: int = Field(..., ge=1, le=65535, description="an allowlisted TCP port of the target")


class UrlArgs(_Args):
    url: str = Field(..., description="an allowlisted HTTP endpoint of the target")


class RunbookArgs(_Args):
    runbook_id: str = Field(..., pattern=r"^RB-[0-9]{3}$", description="a runbook of the library, e.g. RB-009")
    query: str = Field(..., min_length=1, max_length=200, description="what to look for in that runbook")


class HistoryArgs(_Args):
    minutes: int = Field(30, ge=2, le=240, description="window in minutes")


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _fmt(v: Any) -> str:
    return "unknown" if v is None else str(v)


# --- docker_read ---------------------------------------------------------------------------------
def container_list(args: NoArgs, target: TargetRef, info: TargetInfo | None, client) -> CapabilityResult:
    data = client.get("/containers")
    rows = data.get("containers", [])
    text = "; ".join(f"{c.get('name')}={c.get('state')}" for c in rows) or "no in-scope containers"
    return CapabilityResult(values=data, model_text=f"{len(rows)} containers on {target.host}: {text}",
                            source_time=_ts(data.get("collected_at")))


def container_status(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get(f"/containers/{target.name}/status")
    text = (f"{target}: state={_fmt(d.get('state'))} health={_fmt(d.get('health'))} "
            f"restarts={_fmt(d.get('restart_count'))} oom_killed={_fmt(d.get('oom_killed'))} "
            f"exit_code={_fmt(d.get('exit_code'))} started_at={_fmt(d.get('started_at'))} "
            f"memory_limit_bytes={_fmt(d.get('memory_limit_bytes'))} "
            f"networks={','.join(d['networks']) if d.get('networks') is not None else 'unknown'}")
    ident = {"container_id": d["id"]} if d.get("id") else {}
    return CapabilityResult(values=d, model_text=text, source_time=_ts(d.get("collected_at")),
                            identities=ident, units={"memory_limit_bytes": "bytes"})


def container_resources(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get(f"/containers/{target.name}/stats")
    text = (f"{target}: memory={_fmt(d.get('memory_usage_bytes'))}/{_fmt(d.get('memory_limit_bytes'))} bytes "
            f"({_fmt(d.get('memory_percent'))}%), cpu={_fmt(d.get('cpu_percent'))}% of one CPU, "
            f"pids={_fmt(d.get('pids'))}")
    return CapabilityResult(values=d, model_text=text, source_time=_ts(d.get("collected_at")),
                            units={"memory_usage_bytes": "bytes", "memory_limit_bytes": "bytes",
                                   "cpu_percent": "percent of one CPU"})


def container_logs(args: LogsArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get(f"/containers/{target.name}/logs", {"tail": args.tail})
    lines = d.get("lines", [])
    return CapabilityResult(values=d, model_text=f"{target}: last {len(lines)} log lines",
                            source_time=_ts(d.get("collected_at")), partial=bool(d.get("truncated")),
                            coverage=f"last {args.tail} lines requested")


def container_health(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get(f"/containers/{target.name}/health")
    last = (d.get("log") or [{}])[-1]
    text = (f"{target}: health={_fmt(d.get('status'))} failing_streak={_fmt(d.get('failing_streak'))} "
            f"last_exit={_fmt(last.get('exit_code'))} last_output={str(last.get('output', ''))[:160]!r}")
    return CapabilityResult(values=d, model_text=text, source_time=_ts(d.get("collected_at")))


def container_events(args: EventsArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get(f"/containers/{target.name}/events", {"minutes": args.minutes})
    ev = d.get("events", [])
    counts: dict[str, int] = {}
    for e in ev:
        counts[e.get("action", "?")] = counts.get(e.get("action", "?"), 0) + 1
    text = f"{target}: {len(ev)} events in {args.minutes} min: " + ", ".join(f"{k}×{v}" for k, v in sorted(counts.items()))
    return CapabilityResult(values=d, model_text=text, source_time=_ts(d.get("collected_at")),
                            coverage=f"{args.minutes} minutes", partial=bool(d.get("truncated")))


# --- host_probe ----------------------------------------------------------------------------------
def host_cpu(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/cpu")
    return CapabilityResult(values=d, model_text=f"{target.host}: cpu_busy={_fmt(d.get('cpu_busy_percent'))}% "
                            f"load1={_fmt(d.get('load1'))} cpus={_fmt(d.get('cpus'))}",
                            source_time=_ts(d.get("collected_at")), units={"cpu_busy_percent": "percent"})


def host_memory(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/memory")
    return CapabilityResult(values=d, model_text=f"{target.host}: memory total={_fmt(d.get('total_mib'))} MiB "
                            f"available={_fmt(d.get('available_mib'))} MiB swap_used={_fmt(d.get('swap_used_mib'))} MiB",
                            source_time=_ts(d.get("collected_at")),
                            units={"total_mib": "MiB", "available_mib": "MiB", "swap_used_mib": "MiB"})


def host_uptime(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/uptime")
    return CapabilityResult(values=d, model_text=f"{target.host}: uptime={_fmt(d.get('uptime_seconds'))} s",
                            source_time=_ts(d.get("collected_at")), units={"uptime_seconds": "seconds"})


def host_disk(args: DiskArgs, target: TargetRef, info: TargetInfo | None, client) -> CapabilityResult:
    allowed = info.mounts if info else []
    if args.mount not in allowed:
        raise ExecutorError("invalid_args", f"mount {args.mount!r} not allowlisted for {target} (allowed: {allowed})")
    d = client.get("/disk", {"mount": args.mount})
    return CapabilityResult(values=d, model_text=f"{target.host}:{args.mount} used={_fmt(d.get('used_percent'))}% "
                            f"free={_fmt(d.get('free_mib'))} MiB inodes_used={_fmt(d.get('inodes_used_percent'))}%",
                            source_time=_ts(d.get("collected_at")), units={"free_mib": "MiB"})


# --- network_probe -------------------------------------------------------------------------------
def net_dns(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/dns", {"name": target.name})
    return CapabilityResult(values=d, model_text=f"dns {target.name} from {target.host} app network: "
                            f"{'resolved ' + ','.join(d.get('addresses', [])) if d.get('ok') else 'FAILED ' + str(d.get('error'))}",
                            source_time=_ts(d.get("collected_at")))


def net_tcp(args: PortArgs, target: TargetRef, info: TargetInfo | None, client) -> CapabilityResult:
    allowed = info.tcp_ports if info else []
    if args.port not in allowed:
        raise ExecutorError("invalid_args", f"port {args.port} not allowlisted for {target} (allowed: {allowed})")
    d = client.get("/tcp", {"host": target.name, "port": args.port})
    return CapabilityResult(values=d, model_text=f"tcp {target.name}:{args.port} from {target.host} app network: "
                            f"{'ok in ' + str(d.get('duration_ms')) + ' ms' if d.get('ok') else 'FAILED ' + str(d.get('error'))}",
                            source_time=_ts(d.get("collected_at")), units={"duration_ms": "ms"})


def net_http(args: UrlArgs, target: TargetRef, info: TargetInfo | None, client) -> CapabilityResult:
    allowed = info.http_endpoints if info else []
    if args.url not in allowed:
        raise ExecutorError("invalid_args", f"url {args.url!r} not allowlisted for {target} (allowed: {allowed})")
    d = client.get("/http", {"url": args.url})
    return CapabilityResult(values=d, model_text=f"http {args.url}: status={_fmt(d.get('status'))} "
                            f"duration={_fmt(d.get('duration_ms'))} ms error={_fmt(d.get('error'))}",
                            source_time=_ts(d.get("collected_at")), units={"duration_ms": "ms"})


# --- db_probe ------------------------------------------------------------------------------------
def db_health(args: NoArgs, target: TargetRef, info: TargetInfo | None, client) -> CapabilityResult:
    if not (info and info.database):
        raise ExecutorError("invalid_args", f"{target} has no database in the inventory")
    d = client.get("/database/health", {"name": target.name})
    states = ", ".join(f"{k}={v}" for k, v in sorted((d.get("by_state") or {}).items())) or "none"
    clients = ", ".join(f"{c['application_name']}/{c['role']}={c['connections']}" for c in (d.get("by_client") or [])[:5])
    tx = (d.get("longest_transactions") or [None])[0]
    longest = (f"{tx['age_s']} s ({tx['application_name']}, {tx['state']}, wait={tx['wait_event_type']}/{tx['wait_event']})"
               if tx else "none")
    text = (f"database {target.name} ({info.database}): {_fmt(d.get('client_connections'))}/"
            f"{_fmt(d.get('usable_connections'))} client connections ({_fmt(d.get('usage_percent'))}% of usable; "
            f"max_connections={_fmt(d.get('max_connections'))}, reserved={_fmt(d.get('reserved_connections'))}); "
            f"by state: {states}; top clients: {clients or 'none'}; longest open transaction: {longest}; "
            f"lock waits={_fmt(d.get('lock_waits'))}, blocked sessions={_fmt(d.get('blocked_sessions'))}")
    return CapabilityResult(values=d, model_text=text, source_time=_ts(d.get("collected_at")), units={"age_s": "s"})


# --- argus_internal (in-worker) ------------------------------------------------------------------
def knowledge_runbook(args: RunbookArgs, target: TargetRef, info, client) -> CapabilityResult:
    passages = client.runbook(args.runbook_id, args.query)
    rows = [{"runbook_id": p.runbook_id, "version": p.runbook_version, "status": p.runbook_status, "section": p.section,
             # a prefix, as in the recall timeline: a full 64-hex hash reads as a secret to the redactor
             "sha256_prefix": hashlib.sha256(p.text.encode()).hexdigest()[:16], "text": p.text} for p in passages]
    text = "\n".join(f'<passage runbook="{r["runbook_id"]}" version="{r["version"]}" status="{r["status"]}" '
                      f'section="{r["section"]}">\n{r["text"]}\n</passage>' for r in rows)
    return CapabilityResult(values={"runbook_id": args.runbook_id, "passages": rows},
                            model_text=f"{args.runbook_id}: {len(rows)} section(s) for {args.query!r}\n{text}")


# --- prometheus ----------------------------------------------------------------------------------
def _history(signal: str, label: str):
    def impl(args: HistoryArgs, target: TargetRef, info, client) -> CapabilityResult:
        series = client.range(signal, target, args.minutes, step_s=max(15, args.minutes * 60 // 60))
        if not series:
            return CapabilityResult(values={"points": []}, status="error", error_category="not_found",
                                    model_text=f"{label} for {target}: NO DATA in {args.minutes} min (unknown, not zero)",
                                    coverage="no samples")
        vals = [v for _, v in series]
        first, last = vals[0], vals[-1]
        text = (f"{label} for {target} over {args.minutes} min: {len(vals)} samples, first={first:g} "
                f"last={last:g} min={min(vals):g} max={max(vals):g}")
        return CapabilityResult(values={"points": [[t, v] for t, v in series][-60:]}, model_text=text,
                                source_time=datetime.fromtimestamp(series[-1][0], timezone.utc),
                                coverage=f"{len(vals)} samples", partial=len(vals) < 3)
    return impl


def build_catalog() -> list[CapabilitySpec]:
    C, H, N, P = frozenset({"container"}), frozenset({"host"}), frozenset({"container"}), frozenset({"container"})
    return [
        CapabilitySpec("container.list", "get_container_list", "List in-scope containers on the target's host and their state.",
                       "discovering what runs on a host", NoArgs, C | H, 1, "READ_ONLY_SAFE",
                       frozenset({"container", "discovery"}), "docker_read", container_list),
        CapabilitySpec("container.status", "get_container_status",
                       "Container state, health, restart count, OOMKilled flag, exit code, start time, memory limit, "
                       "and the names of the Docker networks it is attached to.",
                       "any container incident; first check; compare the networks of a victim and its dependency "
                       "when a name does not resolve", NoArgs, C, 1, "READ_ONLY_SAFE",
                       frozenset({"container", "stability", "memory"}), "docker_read", container_status),
        CapabilitySpec("container.resources", "get_container_resources",
                       "Current memory usage vs limit, CPU percent and process count of a container.",
                       "memory or CPU pressure is suspected", NoArgs, C, 1, "READ_ONLY_SAFE",
                       frozenset({"container", "memory", "cpu"}), "docker_read", container_resources),
        CapabilitySpec("container.logs", "get_container_logs", "Last N redacted log lines of a container.",
                       "application errors or crash reasons are needed", LogsArgs, C, 1, "READ_ONLY_SENSITIVE",
                       frozenset({"container", "logs", "stability"}), "docker_read", container_logs),
        CapabilitySpec("container.health", "check_container_health", "Docker health-check status and recent probe results.",
                       "a container is reported unhealthy", NoArgs, C, 1, "READ_ONLY_SAFE",
                       frozenset({"container", "availability"}), "docker_read", container_health),
        CapabilitySpec("container.events", "get_container_events", "Docker lifecycle events (start/die/oom/kill/restart) of a container.",
                       "what happened just before a failure", EventsArgs, C, 2, "READ_ONLY_SAFE",
                       frozenset({"container", "stability"}), "docker_read", container_events),
        CapabilitySpec("host.cpu", "get_host_cpu", "Host CPU busy percent and load.", "CPU pressure on the host",
                       NoArgs, H, 1, "READ_ONLY_SAFE", frozenset({"host", "cpu"}), "host_probe", host_cpu),
        CapabilitySpec("host.memory", "get_host_memory", "Host memory total/available and swap.", "host memory pressure",
                       NoArgs, H, 1, "READ_ONLY_SAFE", frozenset({"host", "memory"}), "host_probe", host_memory),
        CapabilitySpec("host.uptime", "get_system_uptime", "Host uptime.", "an unexpected reboot is suspected",
                       NoArgs, H, 1, "READ_ONLY_SAFE", frozenset({"host"}), "host_probe", host_uptime),
        CapabilitySpec("host.disk_usage", "get_disk_usage", "Used/free space and inodes of an allowlisted mount.",
                       "disk filling is suspected", DiskArgs, H, 1, "READ_ONLY_SAFE", frozenset({"host", "disk"}),
                       "host_probe", host_disk),
        CapabilitySpec("network.resolve_dns", "check_dns", "Resolve the target's name from its host's app network.",
                       "a dependency may not be resolvable", NoArgs, N, 1, "READ_ONLY_SAFE",
                       frozenset({"network", "dependency"}), "network_probe", net_dns),
        CapabilitySpec("network.tcp_connect", "check_tcp_connection", "TCP connect to an allowlisted port of the target from its host's app network.",
                       "a dependency may be unreachable", PortArgs, N, 1, "READ_ONLY_SAFE",
                       frozenset({"network", "dependency"}), "network_probe", net_tcp),
        CapabilitySpec("network.http_probe", "check_http_endpoint", "HTTP GET of an allowlisted endpoint: status and latency.",
                       "a web/API endpoint may be failing", UrlArgs, P, 1, "READ_ONLY_SAFE",
                       frozenset({"network", "availability"}), "network_probe", net_http),
        CapabilitySpec("metrics.memory_history", "get_memory_history", "Container memory working set over a time window.",
                       "leak or growth vs spike", HistoryArgs, C, 2, "READ_ONLY_SAFE",
                       frozenset({"memory", "stability"}), "prometheus", _history("container_memory_bytes", "memory bytes")),
        CapabilitySpec("metrics.restart_history", "get_restart_history", "Container restart count over a time window.",
                       "is it a restart loop and since when", HistoryArgs, C, 2, "READ_ONLY_SAFE",
                       frozenset({"stability"}), "prometheus", _history("container_restart_count", "restart count")),
        CapabilitySpec("knowledge.runbook", "query_runbook",
                       "Read sections of a runbook of the library (id, version, status, section).",
                       "the evidence points to a cause another runbook covers (e.g. a branch runbook of the class)",
                       RunbookArgs, C | H, 3, "READ_ONLY_SAFE", frozenset({"knowledge"}), "argus_internal",
                       knowledge_runbook, runs_in="worker", max_output_bytes=16384),
        CapabilitySpec("database.health", "inspect_database_health",
                       "PostgreSQL health read on the target host with a monitoring role: connection slots used vs "
                       "usable, connections by state and by client (application/role), the longest open transactions "
                       "(age, state, wait event) and lock waits. No rows and no SQL text.",
                       "a database may be out of connections, slow, or blocking its clients", NoArgs, C, 3,
                       "READ_ONLY_SAFE", frozenset({"database"}), "db_probe", db_health),
    ]
