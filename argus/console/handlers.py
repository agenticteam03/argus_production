"""ACR-0043 (CON-2): the console's handlers. A handler turns one parsed command into output lines, and every line comes
from a read through `ports` (a capability by the guarded invoke path, a metric, the topology): nothing is typed here.

Write commands never run here (CON-6 adds them). Scenario 2 and 4 read commands have no handler yet (CON-7, CON-8):
`execute` answers `rejected`, "not available yet".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from argus.console.parser import ParsedCommand
from argus.console.registry import LAB_SERVICES, WRITE, help_lines

log = logging.getLogger("argus.console")

DEFAULT_WINDOW_MIN = 30      # a read without --since looks back this far
MAX_WINDOW_MIN = 120         # the log search accepts at most 120 minutes; the console keeps one limit for all reads
# `api cpu` onset: the first sample at or above this share of the way from the window's lowest to its highest value,
# and only when the rise is at least this many cores (below it the series is noise, not an onset)
ONSET_FRACTION = 0.5
ONSET_MIN_RISE = 0.05
ERROR_PATTERNS = ("error", "timeout", "refused")
SAMPLE_LINE_MAX = 160


class HandlerError(Exception):
    """A command that could not give an answer; the message is what the terminal prints."""


@dataclass
class ConsolePorts:
    read: Callable[..., Any]                       # (capability, target_ref, **args) -> Observation (audited, stored)
    service_ref: Callable[[str], str]              # alias ("api") -> "host/container:name"
    host_ref: str                                  # the lab host's target ref
    topology: Callable[[], dict]                   # the live map: {"edges": [...]}
    history: Callable[[str], list[dict]]           # incident id -> its stored console commands, oldest first
    now: Callable[[], datetime]


@dataclass(frozen=True)
class ConsoleResult:
    status: str                                    # ok | error | rejected
    output_lines: list[str]
    started_at: datetime
    finished_at: datetime


def execute(parsed: ParsedCommand, incident_id: str, principal: Any, ports: ConsolePorts) -> ConsoleResult:
    started = ports.now()
    status, lines = _run(parsed, incident_id, ports)
    return ConsoleResult(status, lines, started, ports.now())


def _run(parsed: ParsedCommand, incident_id: str, ports: ConsolePorts) -> tuple[str, list[str]]:
    if parsed.cls == WRITE:
        return "rejected", ["write commands are not enabled yet"]
    handler = HANDLERS.get(parsed.id)
    if handler is None:
        return "rejected", [f"not available yet: {parsed.command.usage}"]
    try:
        return "ok", handler(parsed, incident_id, ports)
    except HandlerError as exc:
        return "error", [str(exc)]
    except Exception:                       # a port's own fault: logged, never shown (it may name internals)
        log.exception("console command %s failed", parsed.id)
        return "error", ["command failed: internal error"]


# --- helpers ---------------------------------------------------------------------------------------------------
def _name(ref: str) -> str:
    return ref.split(":", 1)[-1]


def _ok(observation: Any) -> Any:
    if observation.status != "ok":
        raise HandlerError(observation.model_text or f"read failed: {observation.error_category}")
    return observation


def _window(parsed: ParsedCommand, ports: ConsolePorts) -> int:
    """Minutes to look back: `--since HH:MM` (UTC, today; a time later than now means yesterday) or the default."""
    since = parsed.args.get("since")
    if since is None:
        return DEFAULT_WINDOW_MIN
    now = ports.now().astimezone(timezone.utc)
    hours, minutes = (int(part) for part in since.split(":"))
    start = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    if start > now:
        start -= timedelta(days=1)
    wanted = max(2, -(-int((now - start).total_seconds()) // 60))
    if wanted > MAX_WINDOW_MIN:
        raise HandlerError(f"window too long: at most {MAX_WINDOW_MIN} minutes back; use a later --since")
    return wanted


def _since_value(values: dict) -> Any:
    """A stopped container's state began when it stopped; a running one's when it started."""
    return values.get("finished_at") if values.get("state") not in (None, "running") else values.get("started_at")


def _status_line(name: str, values: dict) -> str:
    parts = [f"state={values.get('state')}"]
    for label, key in (("health", "health"), ("restarts", "restart_count"), ("exit_code", "exit_code")):
        if values.get(key) is not None:
            parts.append(f"{label}={values[key]}")
    since = _since_value(values)
    if since:
        parts.append(f"since={since}")
    return f"{name}: " + " ".join(parts)


# --- meta ------------------------------------------------------------------------------------------------------
def _help(parsed, incident_id, ports) -> list[str]:
    return help_lines()


def _clear(parsed, incident_id, ports) -> list[str]:
    return []


def _history(parsed, incident_id, ports) -> list[str]:
    rows = ports.history(incident_id)
    if not rows:
        return ["No commands yet in this incident."]
    return [f"{row['started_at']:%H:%M:%S}  {row['input']}  [{row['status']}]" for row in rows]


# --- scenario 1 reads ------------------------------------------------------------------------------------------
def _status(parsed, incident_id, ports) -> list[str]:
    lines, failed = [], 0
    for alias in LAB_SERVICES:
        ref = ports.service_ref(alias)
        observation = ports.read("container.status", ref)
        if observation.status == "ok":
            values = observation.values or {}
            lines.append(f"{_name(ref)}: state={values.get('state')} health={values.get('health')}")
        else:
            failed += 1
            lines.append(f"{_name(ref)}: unavailable ({observation.error_category})")
    if failed == len(LAB_SERVICES):
        raise HandlerError("\n".join(lines))
    return lines


def _map(parsed, incident_id, ports) -> list[str]:
    ref = ports.service_ref(parsed.args["service"])
    edges = [e for e in ports.topology().get("edges", []) if ref in (e.get("from"), e.get("to")) and e.get("kind", "dependency") == "dependency"]
    if not edges:
        return [f"{_name(ref)}: no declared dependency edge"]
    lines = []
    for edge in edges:
        text = f"{_name(edge['from'])} -> {_name(edge['to'])}"
        if edge.get("port"):
            text += f" tcp {edge['port']}"
        text += f"  {edge.get('state')}"
        if edge.get("reason"):
            text += f" ({edge['reason']})"
        if edge.get("since"):
            text += f"  since {edge['since']}"
        lines.append(text)
    return lines


def _cache_status(parsed, incident_id, ports) -> list[str]:
    ref = ports.service_ref("cache")
    return [_status_line(_name(ref), _ok(ports.read("container.status", ref)).values or {})]


def _api_errors(parsed, incident_id, ports) -> list[str]:
    minutes, ref = _window(parsed, ports), ports.service_ref("api")
    lines = [f"{_name(ref)} log matches, last {minutes} min:"]
    for pattern in ERROR_PATTERNS:
        values = _ok(ports.read("container.search_logs", ref, pattern=pattern, minutes=minutes)).values or {}
        lines.append(f"  {pattern}: {values.get('matched', 0)}")
        sample = (values.get("lines") or [""])[-1]
        if sample:
            lines.append(f"    last: {str(sample)[:SAMPLE_LINE_MAX]}")
    return lines


def _onset(points: list) -> tuple[float, float] | None:
    """(time, value) of the first sample that rose past ONSET_FRACTION of the window's range, or None."""
    values = [v for _, v in points]
    low, high = min(values), max(values)
    if high - low < ONSET_MIN_RISE:
        return None
    limit = low + ONSET_FRACTION * (high - low)
    return next((t, v) for t, v in points if v >= limit)


def _api_cpu(parsed, incident_id, ports) -> list[str]:
    minutes, ref = _window(parsed, ports), ports.service_ref("api")
    observation = _ok(ports.read("metrics.cpu_history", ref, minutes=minutes))
    points = (observation.values or {}).get("points") or []
    lines = [observation.model_text]
    if not points:
        return lines
    found = _onset(points)
    if found is None:
        lines.append("onset: no rise in this window")
    else:
        lines.append(f"onset: {datetime.fromtimestamp(found[0], timezone.utc):%H:%M:%S}Z "
                     f"at {found[1]:g} cores")
    lines.append(f"latest: {points[-1][1]:g} cores")
    return lines


def _host_metrics(parsed, incident_id, ports) -> list[str]:
    return [_ok(ports.read(capability, ports.host_ref)).model_text
            for capability in ("host.cpu", "host.memory", "host.disk_usage")]


HANDLERS: dict[str, Callable[[ParsedCommand, str, ConsolePorts], list[str]]] = {
    "help": _help, "clear": _clear, "history": _history,
    "status": _status, "map": _map, "cache.status": _cache_status, "api.errors": _api_errors,
    "api.cpu": _api_cpu, "host.metrics": _host_metrics,
}
