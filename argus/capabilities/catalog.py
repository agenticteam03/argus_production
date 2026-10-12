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
    mount: str | None = Field(None, description="an allowlisted mount point of the host; omit it to read every "
                                                "declared mount")


class PortArgs(_Args):
    port: int = Field(..., ge=1, le=65535, description="an allowlisted TCP port of the target")
    attempts: int = Field(1, ge=1, le=5, description="connect attempts 0.5 s apart: more than 1 tells an "
                                                     "intermittent failure from a permanent one")


class ConnectivityArgs(_Args):
    to: str = Field(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
                    description="the destination container's name, on the same host (e.g. a declared dependency)")


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
            f"cpu_limit_cores={_fmt(d.get('cpu_limit_cores'))} "
            f"networks={','.join(d['networks']) if d.get('networks') is not None else 'unknown'}")
    declared = info.networks if info else []
    if declared:                     # E2E-2: the assigned networks (inventory), so a misplaced container is a fact
        text += f" declared_networks={','.join(declared)}"
        missing = [n for n in declared if n not in (d.get("networks") or [])]
        if d.get("networks") is not None and missing:
            text += f" — NOT on its declared network(s): {','.join(missing)}"
    if d.get("host_mounts"):         # E2E-3: the declared host filesystems it has mounted (from the gateway's inspect)
        text += " host_mounts=" + ",".join(f"{m['mount']}({'rw' if m.get('rw') else 'ro'})" for m in d["host_mounts"])
    if d.get("other_binds"):
        text += f" other_binds={d['other_binds']}"
    if d.get("id"):                  # T-0019 batch 2: the host probe names a process's container by this id
        text += f" id={d['id']}"
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
    if args.mount is not None and args.mount not in allowed:
        raise ExecutorError("invalid_args", f"mount {args.mount!r} not allowlisted for {target} (allowed: {allowed})")
    # E2E-2: no mount = every declared mount. The detector fires on the worst declared mount; reading only `/` hid the
    # lab filesystem from the model (SC-05 escalated on "93 % in the metric, 28 % in every read").
    mounts = [args.mount] if args.mount is not None else allowed
    if not mounts:
        raise ExecutorError("invalid_args", f"no declared mount for {target}")
    if args.mount is not None:
        rows = [client.get("/disk", {"mount": args.mount})]
    else:                            # one unreadable mount (409: not mounted) is a stated fact, not a failed read (G-007)
        rows, errors = [], []
        for m in mounts:
            try:
                rows.append(client.get("/disk", {"mount": m}))
            except ExecutorError as e:
                errors.append(e)
                rows.append({"mount": m, "unavailable": e.detail})
        if len(errors) == len(mounts):
            raise errors[0]
    text = "; ".join(f"{target.host}:{m} unavailable ({d['unavailable']})" if "unavailable" in d else
                     f"{target.host}:{m} used={_fmt(d.get('used_percent'))}% free={_fmt(d.get('free_mib'))} MiB "
                     f"inodes_used={_fmt(d.get('inodes_used_percent'))}%" for m, d in zip(mounts, rows))
    values = rows[0] if args.mount is not None else {"mounts": rows}
    times = [t for t in (_ts(d.get("collected_at")) for d in rows) if t]
    return CapabilityResult(values=values, model_text=text, source_time=min(times) if times else None,
                            units={"free_mib": "MiB"})


# T-0019 batch 2 (§4.6, §12.2 Level 2). A key missing from the probe's answer reads as unknown, never zero.
def _pressure(p: dict | None, kind: str) -> str:
    if not p:
        return f"{kind} unknown"
    parts = [f"{k} {_fmt(v.get('avg10'))}%/{_fmt(v.get('avg60'))}%" for k, v in p.items() if isinstance(v, dict)]
    return f"{kind} " + (" ".join(parts) or "unknown")


def host_load(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/load")
    pr = d.get("pressure")
    pressure = ("; ".join(_pressure(pr.get(k), k) for k in ("cpu", "memory", "io")) if isinstance(pr, dict)
                else "unknown")
    return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")),
                            model_text=f"{target.host}: load1={_fmt(d.get('load1'))} load5={_fmt(d.get('load5'))} "
                            f"load15={_fmt(d.get('load15'))} runnable={_fmt(d.get('runnable'))} "
                            f"threads={_fmt(d.get('threads'))} cpus={_fmt(d.get('cpus'))}; pressure stall "
                            f"(share of time waiting, avg10/avg60): {pressure}")


def host_io(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/io")
    rows = d.get("devices")
    if not rows:
        return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")),
                                model_text=f"{target.host}: disk I/O unknown (no block device answered)")
    text = "; ".join(f"{r.get('device')} read={_fmt(r.get('read_kib_s'))} KiB/s ({_fmt(r.get('reads_s'))}/s) "
                     f"write={_fmt(r.get('write_kib_s'))} KiB/s ({_fmt(r.get('writes_s'))}/s) "
                     f"busy={_fmt(r.get('busy_percent'))}%" for r in rows)
    return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")), units={"read_kib_s": "KiB/s"},
                            model_text=f"{target.host} disk I/O over {_fmt(d.get('interval_s'))} s: {text}; "
                            f"pressure stall: {_pressure(d.get('pressure'), 'io')}")


class TopArgs(_Args):
    n: int = Field(5, ge=1, le=10, description="how many processes to list")


def _top(by: str):
    label = {"cpu": "top CPU processes (percent of one core over a short sample)",
             "memory": "top memory processes (resident memory)"}[by]

    def impl(args: TopArgs, target: TargetRef, info, client) -> CapabilityResult:
        d = client.get("/processes", {"by": by, "n": args.n})
        rows = d.get("processes")
        if rows is None:
            return CapabilityResult(values=d, model_text=f"{target.host}: {label} unknown",
                                    source_time=_ts(d.get("collected_at")))

        def one(p: dict) -> str:
            where = ("kernel thread" if p.get("kernel_thread") else
                     f"container {p['container_id']}" if p.get("container_id") else "host")
            cpu = f" {_fmt(p.get('cpu_percent'))}%" if by == "cpu" else ""
            return f"pid {p.get('pid')} {p.get('command')} ({where}){cpu} rss={_fmt(p.get('rss_mib'))} MiB"
        text = "; ".join(one(p) for p in rows) or "no process read"
        extra = f"; sample {d['sample_s']} s, cpus={_fmt(d.get('cpus'))}" if by == "cpu" and d.get("sample_s") else ""
        return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")), partial=bool(d.get("truncated")),
                                model_text=f"{target.host} {label}: {text}{extra} (containers by id: compare "
                                           f"get_container_status id=)")
    return impl


def host_sockets(args: NoArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/sockets")
    states = d.get("tcp_by_state")
    if states is None:
        return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")),
                                model_text=f"{target.host}: host socket summary unknown")
    tcp = (d.get("sockstat") or {}).get("TCP") or {}
    return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")), partial=bool(d.get("truncated")),
                            model_text=f"{target.host} host network namespace: TCP "
                            + (" ".join(f"{k}={v}" for k, v in states.items()) or "none")
                            + f"; listening ports {','.join(str(p) for p in d.get('listening_ports') or []) or 'none'}"
                            + f"; sockstat TCP inuse={_fmt(tcp.get('inuse'))} orphan={_fmt(tcp.get('orphan'))} "
                              f"tw={_fmt(tcp.get('tw'))}")


class FileArgs(_Args):
    path: str = Field(..., min_length=2, max_length=512, description="an absolute file path the inspection policy "
                                                                       "allows for this target")
    lines: int = Field(100, ge=1, le=500, description="the most recent lines to read")


class ConfigArgs(_Args):
    path: str | None = Field(None, max_length=512, description="omit it: every configuration file the inspection "
                                                               "policy lists for this target")


class JournalArgs(_Args):
    unit: str = Field(..., pattern=r"^[A-Za-z0-9@_.-]{1,128}$", description="an allowlisted systemd unit, e.g. "
                                                                          "docker.service")
    lines: int = Field(50, ge=1, le=200, description="the most recent lines of that unit")


class PidArgs(_Args):
    pid: int = Field(..., ge=1, le=4194304, description="a process id, e.g. from get_top_cpu_processes")


class MountArgs(_Args):
    mount: str = Field(..., description="a declared mount point of the host (as in get_disk_usage)")


def host_directory_sizes(args: MountArgs, target: TargetRef, info: TargetInfo | None, client) -> CapabilityResult:
    allowed = info.mounts if info else []
    if args.mount not in allowed:
        raise ExecutorError("invalid_args", f"mount {args.mount!r} not allowlisted for {target} (allowed: {allowed})")
    d = client.get("/directory_sizes", {"path": args.mount})
    rows = d.get("children")
    if rows is None:
        return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")),
                                model_text=f"{target.host}:{args.mount} directory sizes unknown")
    text = ", ".join(f"{c.get('name')} {_fmt(c.get('mib'))} MiB" + ("" if c.get("complete", True) else " (partial)")
                     for c in rows) or "empty"
    done = d.get("complete") is True
    tail = ("complete" if done else f"partial: stopped after {_fmt(d.get('entries_read'))} entries (limit "
            f"{_fmt(d.get('limit_entries'))} entries / {_fmt(d.get('limit_seconds'))} s), sizes are at least these")
    return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")), partial=not done,
                            model_text=f"{target.host}:{args.mount} largest entries: {text}; {tail}")


class OomArgs(_Args):
    minutes: int = Field(60, ge=1, le=1440, description="lookback window in minutes")


def host_kernel_oom(args: OomArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/oom", {"minutes": args.minutes})
    since_boot = f"; oom_kill since boot={_fmt(d.get('oom_kill_since_boot'))}"
    if d.get("source") == "unavailable":
        return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")),
                                model_text=f"{target.host}: kernel OOM records unknown (no kernel log on this host)"
                                           + since_boot)
    total, window = d.get("records_total"), d.get("window_minutes", args.minutes)
    partial = d.get("complete") is not True
    note = " (partial read: older records may exist)" if partial else ""
    if total is None:
        text = "kernel OOM records unknown"
    elif total == 0:
        text = f"no kernel OOM kill in the last {window} min{note}"
    else:
        by = ", ".join(f"{c.get('container_id') or 'host-wide'}×{c.get('count')}" for c in d.get("by_container") or [])
        last = (d.get("records") or [{}])[-1]
        where = f"container {last['container_id']}" if last.get("container_id") else "host-wide"
        text = (f"{total} kernel OOM kill(s) in the last {window} min{note}; by container: {by}; latest: "
                f"{last.get('time')} {last.get('scope')} {where} {last.get('command')} pid {last.get('pid')} "
                f"anon_rss={_fmt(last.get('anon_rss_mib'))} MiB")
    return CapabilityResult(values=d, source_time=_ts(d.get("collected_at")), partial=partial,
                            model_text=f"{target.host}: {text}{since_boot}")


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
    params = {"host": target.name, "port": args.port}
    if args.attempts > 1:                                  # T-0019 batch 3c; one attempt = the old request
        params["attempts"] = args.attempts
    d = client.get("/tcp", params)
    text = (f"tcp {target.name}:{args.port} from {target.host} app network: "
            f"{'ok in ' + str(d.get('duration_ms')) + ' ms' if d.get('ok') else 'FAILED ' + str(d.get('error'))}")
    tries = d.get("attempts")
    if isinstance(tries, list) and len(tries) > 1:
        each = ", ".join(f"{'ok' if t.get('ok') else 'FAIL'} {t.get('duration_ms')} ms" for t in tries)
        text = (f"tcp {target.name}:{args.port} from {target.host} app network: {_fmt(d.get('succeeded'))}/{len(tries)} "
                f"connected ({each})")
    return CapabilityResult(values=d, model_text=text, source_time=_ts(d.get("collected_at")), units={"duration_ms": "ms"})


def _side(s: dict, name: str) -> str:
    nets, running = s.get("networks"), s.get("running")
    state = "running" if running else "not running" if running is False else "state unknown"
    where = ",".join(nets) if nets else ("no network" if nets == [] else "unknown networks")
    return f"{name} ({state}) on {where}"


def net_connectivity(args: ConnectivityArgs, target: TargetRef, info, client) -> CapabilityResult:
    """T-0019 batch 3c (§12.2 `check_connectivity`): both sides' networks and the shared ones, from the read gateway."""
    if args.to == target.name:
        raise ExecutorError("invalid_args", f"{target} and the destination are the same container")
    d = client.get("/connectivity", {"from": target.name, "to": args.to})
    src, dst, shared = d.get("from") or {}, d.get("to") or {}, d.get("shared")
    if shared is None or src.get("networks") is None or dst.get("networks") is None:
        verdict = "shared networks unknown"
    elif shared:
        verdict = f"shared networks: {','.join(shared)}"
    else:
        verdict = "NO shared network: they cannot reach each other on a common network"
    return CapabilityResult(values=d, model_text=f"connectivity {target.host}: {_side(src, target.name)} -> "
                            f"{_side(dst, args.to)}; {verdict}", source_time=_ts(d.get("collected_at")))


def net_http(args: UrlArgs, target: TargetRef, info: TargetInfo | None, client) -> CapabilityResult:
    allowed = info.http_endpoints if info else []
    if args.url not in allowed:
        raise ExecutorError("invalid_args", f"url {args.url!r} not allowlisted for {target} (allowed: {allowed})")
    d = client.get("/http", {"url": args.url})
    return CapabilityResult(values=d, model_text=f"http {args.url}: status={_fmt(d.get('status'))} "
                            f"duration={_fmt(d.get('duration_ms'))} ms error={_fmt(d.get('error'))}",
                            source_time=_ts(d.get("collected_at")), units={"duration_ms": "ms"})


# --- T-0019 batch 3b: Level 3 reads under the inspection policy (§4.7) ----------------------------------------------
def host_read_file(args: FileArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/read_file", {"target": str(target), "path": args.path, "lines": args.lines})
    rows = d.get("lines") or []
    text = (f"file {args.path} on {target}: last {len(rows)} line(s){' (more before)' if d.get('truncated') else ''}\n"
            + "\n".join(rows))
    return CapabilityResult(values=d, model_text=text, source_time=_ts(d.get("collected_at")),
                            truncated=bool(d.get("truncated")))


def host_service_config(args: ConfigArgs, target: TargetRef, info, client) -> CapabilityResult:
    params = {"target": str(target)}
    if args.path:
        params["path"] = args.path
    d = client.get("/service_config", params)
    files = d.get("files")
    if not files:
        return CapabilityResult(values=d, status="error", error_category="not_found",
                                model_text=f"service configuration of {target}: none returned (unknown)")
    text = "\n".join(f"<config path=\"{f.get('path')}\"{' truncated=\"true\"' if f.get('truncated') else ''}>\n"
                     f"{f.get('text', '')}\n</config>" for f in files)
    return CapabilityResult(values=d, model_text=f"service configuration of {target} ({len(files)} file(s)):\n{text}",
                            source_time=_ts(d.get("collected_at")))


def host_journal(args: JournalArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/journal", {"target": str(target), "unit": args.unit, "lines": args.lines})
    if d.get("source") != "syslog" or d.get("lines") is None:
        return CapabilityResult(values=d, status="error", error_category="not_found",
                                model_text=f"journal of {args.unit} on {target}: no log source (unknown, not quiet)")
    rows = d["lines"]
    head = (f"journal of {args.unit} on {target} (syslog, program {d.get('program')}): {len(rows)} line(s)"
            f"{'' if d.get('window_complete', True) else ' from the last part of the log only'}")
    return CapabilityResult(values=d, model_text=head + ("\n" + "\n".join(rows) if rows else ": none in the window"),
                            source_time=_ts(d.get("collected_at")))


def host_process_details(args: PidArgs, target: TargetRef, info, client) -> CapabilityResult:
    d = client.get("/process_details", {"target": str(target), "pid": args.pid})
    lim = (d.get("limits") or {}).get("max_open_files") or [None, None]
    text = (f"pid {d.get('pid')} {d.get('name')} on {target}: state={_fmt(d.get('state'))} "
            f"threads={_fmt(d.get('threads'))} rss={_fmt(d.get('rss_mib'))} MiB peak={_fmt(d.get('hwm_mib'))} MiB "
            f"open files {_fmt(d.get('open_files'))} / {_fmt(lim[0])} container={d.get('container_id') or 'host'}")
    return CapabilityResult(values=d, model_text=text, source_time=_ts(d.get("collected_at")))


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
    if d.get("monitor_slot_reserved") is False:            # OP-010: at 100 % this probe could not connect
        text += "; monitoring slot not reserved (the probe can be locked out when every ordinary slot is taken)"
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


# --- §12.7 combined (T-0034): sub-reads through InvokeCapability, never an executor ---------------------------------
SNAPSHOT_READS = (("container.status", "self", {}), ("container.resources", "self", {}),
                  ("container.logs", "self", {"tail": 30}), ("host.memory", "host", {}), ("host.cpu", "host", {}))


def diagnostic_snapshot(args: NoArgs, target: TargetRef, info, invoker) -> CapabilityResult:
    """One container's status, resources and recent logs, and its host's memory and CPU, in one result."""
    host = TargetRef.parse(f"{target.host}/host:{target.host}")
    rows, statuses = [], {}
    for name, who, extra in SNAPSHOT_READS:
        obs, ref = invoker.read(name, target if who == "self" else host, extra)
        statuses[name] = obs.status
        rows.append(f"[{ref.evidence_id if ref else 'no evidence'}] {obs.model_text[:400]}")
    failed = [n for n, s in statuses.items() if s != "ok"]
    head = f"diagnostic snapshot of {target} ({len(rows) - len(failed)}/{len(rows)} reads ok"
    head += f"; not ok: {', '.join(failed)})" if failed else ")"
    return CapabilityResult(values={"statuses": statuses}, model_text=head + "\n" + "\n".join(rows),
                            partial=bool(failed))

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
                       "the names of the Docker networks it is attached to, and the host's declared filesystems it "
                       "has mounted (rw/ro).",
                       "any container incident; first check; compare the networks of a victim and its dependency "
                       "when a name does not resolve; in a disk incident, which container writes the full "
                       "filesystem", NoArgs, C, 1, "READ_ONLY_SAFE",
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
        CapabilitySpec("host.disk_usage", "get_disk_usage",
                       "Used/free space and inodes of an allowlisted mount, or of every declared mount when none is given.",
                       "disk filling is suspected", DiskArgs, H, 1, "READ_ONLY_SAFE", frozenset({"host", "disk"}),
                       "host_probe", host_disk),
        # T-0019 batch 2 (Level 2). Tags decide which classes are offered them: no `host` tag, so a class gets only
        # the ones its own resource tag asks for; `sockets` is used by no class yet (the lab's traffic is inside
        # Docker networks, not the host's namespace).
        CapabilitySpec("host.load", "get_host_load",
                       "Host load averages (1/5/15 min), runnable tasks and pressure stall (cpu, memory, io).",
                       "the host may be overloaded or tasks are waiting for CPU, memory or I/O", NoArgs, H, 2,
                       "READ_ONLY_SAFE", frozenset({"cpu"}), "host_probe", host_load),
        CapabilitySpec("host.top_cpu", "get_top_cpu_processes",
                       "The host's processes using the most CPU over a short sample: command name, container id, "
                       "percent of one core.", "which process or container burns the host's CPU", TopArgs, H, 2,
                       "READ_ONLY_SENSITIVE", frozenset({"cpu"}), "host_probe", _top("cpu")),
        CapabilitySpec("host.top_memory", "get_top_memory_processes",
                       "The host's processes using the most resident memory: command name, container id, RSS.",
                       "which process or container holds the host's memory", TopArgs, H, 2,
                       "READ_ONLY_SENSITIVE", frozenset({"memory"}), "host_probe", _top("memory")),
        CapabilitySpec("host.kernel_oom_records", "get_kernel_oom_records",
                       "Kernel OOM-killer records in a time window: count by container id, the latest kill "
                       "(container or host-wide, command, memory).",
                       "a process may have been killed for memory by the kernel (exit 137, OOM)", OomArgs, H, 2,
                       "READ_ONLY_SENSITIVE", frozenset({"memory", "stability"}), "host_probe", host_kernel_oom),
        CapabilitySpec("host.io", "get_io_metrics",
                       "Disk I/O of the host's block devices over a 1 s sample: KiB/s, operations/s, busy percent, "
                       "I/O pressure stall.", "disk writes or I/O saturation are suspected", NoArgs, H, 2,
                       "READ_ONLY_SAFE", frozenset({"disk"}), "host_probe", host_io),
        CapabilitySpec("host.directory_sizes", "get_directory_sizes",
                       "The largest entries directly under a declared mount (one filesystem, bounded walk).",
                       "which directory fills a filesystem", MountArgs, H, 2, "READ_ONLY_SAFE",
                       frozenset({"disk"}), "host_probe", host_directory_sizes),
        CapabilitySpec("host.read_file", "inspect_approved_file",
                       "The last lines of a file the inspection policy allows for this target.",
                       "a specific log or diagnostics file is named by the evidence", FileArgs, C | H, 3,
                       "READ_ONLY_SENSITIVE", frozenset({"files"}), "host_probe", host_read_file),
        CapabilitySpec("host.service_config", "inspect_service_config",
                       "The configuration files of this target that the inspection policy lists (e.g. a proxy's "
                       "timeouts and upstreams).", "the failure may come from a configured limit or route, such as "
                       "a proxy timeout", ConfigArgs, C | H, 3, "READ_ONLY_SENSITIVE", frozenset({"config"}),
                       "host_probe", host_service_config),
        CapabilitySpec("host.journal", "get_journal_logs",
                       "Recent log lines of an allowlisted systemd unit of the host (e.g. the Docker daemon).",
                       "a container problem may come from the Docker or containerd daemon", JournalArgs, H, 3,
                       "READ_ONLY_SENSITIVE", frozenset({"journal"}), "host_probe", host_journal),
        CapabilitySpec("host.process_details", "inspect_process_details",
                       "One process of the host: state, threads, memory, open files against its limit, container.",
                       "one process (from the top lists) needs a closer look", PidArgs, H, 3, "READ_ONLY_SENSITIVE",
                       frozenset({"process"}), "host_probe", host_process_details),
        CapabilitySpec("host.socket_summary", "get_socket_summary",
                       "TCP sockets of the host's own network namespace by state, and its listening ports.",
                       "a host-level service may be leaking or refusing connections", NoArgs, H, 2,
                       "READ_ONLY_SAFE", frozenset({"sockets"}), "host_probe", host_sockets),
        CapabilitySpec("network.resolve_dns", "check_dns", "Resolve the target's name from its host's app network.",
                       "a dependency may not be resolvable", NoArgs, N, 1, "READ_ONLY_SAFE",
                       frozenset({"network", "dependency"}), "network_probe", net_dns),
        CapabilitySpec("network.tcp_connect", "check_tcp_connection", "TCP connect to an allowlisted port of the target from its host's app network.",
                       "a dependency may be unreachable", PortArgs, N, 1, "READ_ONLY_SAFE",
                       frozenset({"network", "dependency"}), "network_probe", net_tcp),
        CapabilitySpec("network.connectivity", "check_connectivity",
                       "The networks of this container and of a destination container on the same host, and the ones "
                       "they share (names only).", "a dependency is unreachable although it is running: are both "
                       "sides on a common network?", ConnectivityArgs, C, 2, "READ_ONLY_SAFE",
                       frozenset({"connectivity"}), "docker_read", net_connectivity),
        CapabilitySpec("network.http_probe", "check_http_endpoint", "HTTP GET of an allowlisted endpoint: status and latency.",
                       "a web/API endpoint may be failing", UrlArgs, P, 1, "READ_ONLY_SAFE",
                       frozenset({"network", "availability"}), "network_probe", net_http),
        CapabilitySpec("metrics.memory_history", "get_memory_history", "Container memory working set over a time window.",
                       "leak or growth vs spike", HistoryArgs, C, 2, "READ_ONLY_SAFE",
                       frozenset({"memory", "stability"}), "prometheus", _history("container_memory_bytes", "memory bytes")),
        CapabilitySpec("metrics.restart_history", "get_restart_history", "Container restart count over a time window.",
                       "is it a restart loop and since when", HistoryArgs, C, 2, "READ_ONLY_SAFE",
                       frozenset({"stability"}), "prometheus", _history("container_restart_count", "restart count")),
        CapabilitySpec("analysis.diagnostic_snapshot", "capture_diagnostic_snapshot",
                       "A container's status, resources and recent logs, and its host's memory and CPU, in one call "
                       "(each part stored as its own evidence).", "a first broad look at a container and its host",
                       NoArgs, C, 3, "READ_ONLY_SAFE", frozenset({"snapshot"}), "argus_internal", diagnostic_snapshot,
                       runs_in="worker", max_output_bytes=16384, max_subcalls=6),
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
                       "READ_ONLY_SENSITIVE", frozenset({"database"}), "db_probe", db_health),   # RB-004: client names
    ]
