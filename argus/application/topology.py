"""ACR-0017: the system map for the UI (`GET /api/v1/topology[?incident_id=<id>]`).

Built from what Argus already holds, with no new read on the hosts:
- the inventory: targets, declared dependencies with their ports, declared networks;
- the latest named signals per container (restarts, health, memory, CPU quota) through the MetricsPort;
- the exporter's probe of each declared dependency (`MetricsPort.dependency_probes`, ACR-0021): one state per link;
- with an incident, its stored `container.status` evidence for its target and root cause (their real state, networks
  and memory limit at the time of the incident), the roles of the boxes and the path from the target to the cause.

Shown on purpose: container names, Docker networks, dependency ports. Never: VM addresses, Argus's internal endpoints
(executor and Alertmanager URLs), tokens or secrets. A value Argus does not know is `unknown`, never ok.
"""
from __future__ import annotations

import copy
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from argus.domain.model import EvidenceRecord, Incident, TargetRef
from argus.ports.ports import MetricsUnavailable, StaleMetrics

CONTAINER_SIGNALS = {"restarts_10m", "health_unhealthy", "dependency_probe_min", "container_memory_bytes",
                     "container_cpu_quota_used_ratio_5m"}
HOST_SIGNALS = {"host_cpu_busy_ratio"}
STATES = ("running", "restarting", "unhealthy", "stopped", "unknown")
DOCKER_STATE = {"running": "running", "restarting": "restarting", "exited": "stopped", "dead": "stopped",
                "created": "stopped", "paused": "stopped"}
LINK_WARNING_MS = 100.0                    # a dependency answer slower than this is `slow` (inventory: link_warning_ms)
MEMORY_WARNING, MEMORY_CRITICAL = 0.8, 0.9   # of the container's memory limit, known only from an incident's evidence


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _mib(value: Any) -> str | None:
    return f"{round(value / 1048576)} MiB" if isinstance(value, (int, float)) and value > 0 else None


def _problem(kind: str, severity: str, summary: str, signal: str, value: float, threshold: float, unit: str) -> dict:
    return {"kind": kind, "severity": severity, "summary": summary, "signal": signal, "value": value,
            "threshold": threshold, "unit": unit}


def _crossed(value: float | None, line) -> tuple[str, float] | None:
    """('critical' | 'warning', the line crossed) when `value` is past a threshold of `line` (B1), else None."""
    if value is None or line is None:
        return None
    past = (lambda a, b: a >= b) if line.direction == "above" else (lambda a, b: a <= b)
    if past(value, line.critical):
        return "critical", line.critical
    if past(value, line.warning):
        return "warning", line.warning
    return None


class Topology:
    def __init__(self, inventory, metrics, store, home_host: str | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 clock: Callable[[], float] = time.monotonic, ttl_s: float = 20, ttl_closed_s: float = 600,
                 thresholds=None):
        self.inventory, self.metrics, self.store = inventory, metrics, store
        self.home_host = home_host or None
        self.thresholds = thresholds
        self.now, self.clock, self.ttl_s, self.ttl_closed_s = now, clock, ttl_s, ttl_closed_s
        self._global: tuple[float, dict, dict] | None = None      # (expires, the answer, the readings behind it)
        self._overlays: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    # --- the global map (shared by every viewer for ttl_s) ------------------------------------------------------
    def view(self) -> dict:
        return self._shared()[0]

    def _shared(self) -> tuple[dict, dict]:
        with self._lock:
            if self._global and self._global[0] > self.clock():
                return self._global[1], self._global[2]
        answer, values = self._build()
        with self._lock:
            self._global = (self.clock() + self.ttl_s, answer, values)
        return answer, values

    def _line(self, signal: str):
        return self.thresholds.get(signal) if self.thresholds else None

    def _build(self) -> tuple[dict, dict]:
        hosts = sorted(h.name for h in self.inventory.hosts())
        down: set[str] = set()                                      # hosts whose monitoring cannot be reached
        values: dict[str, dict] = {}
        for t in self.inventory.targets():
            if t.ref.host in down:
                values[str(t.ref)] = {}
                continue
            signals = CONTAINER_SIGNALS if t.ref.kind == "container" else HOST_SIGNALS
            try:
                values[str(t.ref)] = dict(self.metrics.snapshot(t.ref, signals).values)
            except MetricsUnavailable:
                down.add(t.ref.host)
                values[str(t.ref)] = {}
            except (StaleMetrics, ValueError):
                values[str(t.ref)] = {}
        ports = {str(t.ref): list(t.tcp_ports) for t in self.inventory.targets()}
        nodes, edges = [], []
        for t in sorted(self.inventory.targets(), key=lambda x: str(x.ref)):
            ref, vals = str(t.ref), values.get(str(t.ref), {})
            info = []
            if t.networks:
                info.append({"label": "Declared networks", "value": ", ".join(t.networks)})
            if t.tcp_ports:
                info.append({"label": "Ports", "value": ", ".join(str(p) for p in t.tcp_ports)})
            if t.database:
                info.append({"label": "Database", "value": t.database})
            if vals.get("restarts_10m") is not None:
                info.append({"label": "Restarts (10 min)", "value": f"{vals['restarts_10m']:g}"})
            if vals.get("health_unhealthy") is not None:
                info.append({"label": "Health", "value": "unhealthy" if vals["health_unhealthy"] >= 1 else "ok"})
            status = self._status(t.ref, vals)
            node = {"id": ref, "host": t.ref.host, "label": t.ref.name, "target": ref, "kind": t.ref.kind,
                    "sub": "host" if t.ref.kind == "host" else ("database container" if t.database else "container"),
                    "status": status, "info": info, "networks": list(t.networks), "role": None}
            self._judge(node, t.profile, vals, memory_limit=None, running_seen=False)
            nodes.append(node)
            edges += self._links(t, vals, ports, down)
        if self.home_host in hosts:
            for h in hosts:
                if h != self.home_host:
                    a, b = f"{self.home_host}/host:{self.home_host}", f"{h}/host:{h}"
                    edges.append({"id": f"{a}->{b}:read", "kind": "argus_reads", "from": a, "to": b, "port": None,
                                  "state": "read", "label": "Argus reads", "checked_at": None, "latency_ms": None,
                                  "reason": None})
        answer = {"observed_at": _iso(self.now()),
                  "hosts": [{"id": h, "label": h, "role": "argus" if h == self.home_host else "monitored"}
                            for h in hosts],
                  "nodes": nodes, "edges": edges}
        return answer, values

    # --- one link per declared dependency ---------------------------------------------------------------------------
    def _links(self, t, vals: dict, ports: dict, down: set[str]) -> list[dict]:
        if not t.depends_on:
            return []
        probes: dict = {}
        if t.ref.kind == "container" and t.ref.host not in down:
            try:
                probes = self.metrics.dependency_probes(t.ref) or {}
            except MetricsUnavailable:
                down.add(t.ref.host)
            except (StaleMetrics, ValueError):
                probes = {}
        warn = t.link_warning_ms or LINK_WARNING_MS
        edges = []
        for dep in t.depends_on:
            d = str(dep)
            port = ports.get(d, [None])[0] if ports.get(d) else None
            sample = probes.get(dep.name) if dep.host == t.ref.host else None
            state, checked, latency = "unknown", None, None
            if sample is not None:
                checked = _iso(sample.at)
                latency = None if sample.duration_s is None else round(sample.duration_s * 1000, 3)
                if sample.success is not None and port is not None:
                    state = "broken" if sample.success < 1 else ("slow" if latency is not None and latency > warn else "ok")
            elif (len(t.depends_on) == 1 and t.ref.kind == "container" and dep.kind == "container" and port is not None
                  and vals.get("dependency_probe_min") is not None):
                state = "ok" if vals["dependency_probe_min"] >= 1 else "broken"   # no per-dependency sample: the minimum
            reason = "not reachable" if state == "broken" else None
            label = (f"tcp {port}" if port else "declared dependency") + (" · not reachable" if state == "broken" else "")
            edges.append({"id": f"{t.ref}->{d}:{port if port is not None else ''}", "kind": "dependency", "from": str(t.ref), "to": d, "port": port,
                          "state": state, "label": label, "checked_at": checked, "latency_ms": latency, "reason": reason})
        return edges

    # --- health and problems of one box -----------------------------------------------------------------------------
    def _judge(self, node: dict, profile: str | None, vals: dict, memory_limit: float | None, running_seen: bool) -> None:
        """`problems`, `health` and `idle` from the box's status and readings. `running_seen`: the incident's evidence
        says the container runs (so an empty reading is a monitoring gap, not a stopped box)."""
        problems = []
        if node["kind"] == "container":
            r = _crossed(vals.get("restarts_10m"), self._line("restarts_10m"))
            if r:
                n = vals["restarts_10m"]
                problems.append(_problem("restarts", r[0], f"{n:g} restarts in the last 10 minutes", "restarts_10m",
                                         n, r[1], ""))
            if (vals.get("health_unhealthy") or 0) >= 1:
                problems.append(_problem("unhealthy", "warning", "The Docker health check reports unhealthy",
                                         "health_unhealthy", vals["health_unhealthy"], 1, ""))
            q = _crossed(vals.get("container_cpu_quota_used_ratio_5m"), self._line("container_cpu_quota_used_ratio_5m"))
            if q:
                pct = round(vals["container_cpu_quota_used_ratio_5m"] * 100, 6)
                problems.append(_problem("cpu_quota", q[0], f"Using {pct:g}% of its CPU quota",
                                         "container_cpu_quota_used_ratio_5m", pct, round(q[1] * 100, 6), "%"))
            used = vals.get("container_memory_bytes")
            if memory_limit and used is not None:
                ratio = used / memory_limit
                sev = "critical" if ratio >= MEMORY_CRITICAL else "warning" if ratio >= MEMORY_WARNING else None
                if sev:
                    line = MEMORY_CRITICAL if sev == "critical" else MEMORY_WARNING
                    problems.append(_problem("memory", sev,
                                             f"Memory at {used / 1048576:.1f} MiB of {memory_limit / 1048576:.0f} MiB",
                                             "container_memory_bytes", round(used / 1048576, 1),
                                             round(line * memory_limit / 1048576, 1), "MiB"))
            if running_seen and all(v is None for v in vals.values()):
                problems.append(_problem("stale_metrics", "warning", "Running, but no fresh metric samples",
                                         "container_memory_bytes", None, None, ""))
        status = node["status"]
        if profile == "scenario" and status in ("unknown", "stopped"):
            health = "idle"
        elif status == "stopped" or any(p["severity"] == "critical" for p in problems):
            health = "failed"
        elif status in ("unhealthy", "restarting") or problems:
            health = "degraded"
        elif status == "unknown":
            health = "unknown"
        else:
            health = "healthy"
        node.update(problems=problems, health=health, idle=health == "idle")

    @staticmethod
    def _status(ref: TargetRef, vals: dict) -> str:
        if not vals or all(v is None for v in vals.values()):
            return "unknown"
        if ref.kind != "container":
            return "running"
        if (vals.get("restarts_10m") or 0) > 0:
            return "restarting"
        if (vals.get("health_unhealthy") or 0) >= 1:
            return "unhealthy"
        return "running" if vals.get("restarts_10m") is not None else "unknown"

    # --- one incident's overlay (its stored evidence) -------------------------------------------------------------
    def view_for(self, inc: Incident) -> dict:
        with self._lock:
            hit = self._overlays.get(inc.id)
            if hit and hit[0] > self.clock():
                return hit[1]
        shared, values = self._shared()
        answer = self._overlay(inc, copy.deepcopy(shared), values)
        with self._lock:
            self._overlays[inc.id] = (self.clock() + (self.ttl_closed_s if inc.closed_at else self.ttl_s), answer)
            if len(self._overlays) > 200:
                now = self.clock()
                self._overlays = {k: v for k, v in self._overlays.items() if v[0] > now}
        return answer

    def _overlay(self, inc: Incident, body: dict, values: dict) -> dict:
        body["incident_id"] = inc.id
        involved = {str(inc.target)} | ({inc.root_cause_target} if inc.root_cause_target else set())
        latest: dict[str, EvidenceRecord] = {}
        for e in self.store.list_evidence(inc.id):
            if e.capability == "container.status" and e.status == "ok" and e.target in involved:
                if e.target not in latest or e.collected_at >= latest[e.target].collected_at:
                    latest[e.target] = e
        nets: dict[str, list[str]] = {}
        for node in body["nodes"]:
            rec = latest.get(node["target"])
            if rec is None:
                continue
            data = (rec.values or {}).get("values") or {}
            node["status"] = self._docker_status(data)
            extra = []
            if isinstance(data.get("networks"), list):
                nets[node["target"]] = [str(n) for n in data["networks"]]
                node["networks"] = nets[node["target"]]
                extra.append({"label": "Networks (at the incident)", "value": ", ".join(nets[node["target"]]) or "none"})
            if isinstance(data.get("restart_count"), (int, float)):
                extra.append({"label": "Restarts (at the incident)", "value": f"{data['restart_count']:g}"})
            if _mib(data.get("memory_limit_bytes")):
                extra.append({"label": "Memory limit", "value": _mib(data["memory_limit_bytes"])})
            if data.get("exit_code") is not None:
                extra.append({"label": "Last exit code", "value": str(data["exit_code"])})
            if data.get("oom_killed") is True:
                extra.append({"label": "OOM killed", "value": "yes"})
            # what the incident saw comes first; the inventory's declared networks move to the end for comparison
            declared = [i for i in node["info"] if i["label"] == "Declared networks"]
            others = [i for i in node["info"] if i["label"] != "Declared networks"]
            node["info"] = extra + others + declared
            limit = data.get("memory_limit_bytes")
            info = self.inventory.target(TargetRef.parse(node["target"]))
            self._judge(node, info.profile if info else None, values.get(node["target"], {}),
                        memory_limit=limit if isinstance(limit, (int, float)) and limit > 0 else None,
                        running_seen=node["status"] in ("running", "unhealthy", "restarting"))
        for edge in body["edges"]:
            a, b = nets.get(edge["from"]), nets.get(edge["to"])
            if a is not None and b is not None and not set(a) & set(b):
                edge["state"] = "broken"
                edge["reason"] = "no shared network"
                edge["label"] = (f"tcp {edge['port']} · " if edge.get("port") else "") + "no shared network"
        self._cause(inc, body)
        return body

    def _cause(self, inc: Incident, body: dict) -> None:
        """Roles of the boxes and the shortest path over declared dependencies from the target to its root cause."""
        target, root = str(inc.target), inc.root_cause_target
        graph: dict[str, list[str]] = {}
        for e in body["edges"]:
            if e["kind"] == "dependency":
                graph.setdefault(e["from"], []).append(e["to"])
        path: list[str] = []
        if root and root == target:
            path = [target]
        elif root:
            seen, queue = {target: None}, deque([target])
            while queue and root not in seen:
                here = queue.popleft()
                for nxt in graph.get(here, []):
                    if nxt not in seen:
                        seen[nxt] = here
                        queue.append(nxt)
            if root in seen:
                step = root
                while step is not None:
                    path.append(step)
                    step = seen[step]
                path.reverse()
        body["cause_path"] = path
        for node in body["nodes"]:
            t = node["target"]
            node["role"] = ("root_cause" if t == root else "affected" if t == target
                            else "on_path" if t in path else None)

    @staticmethod
    def _docker_status(data: dict) -> str:
        state = DOCKER_STATE.get(str(data.get("state") or "").lower(), "unknown")
        if state == "running" and str(data.get("health") or "").lower() == "unhealthy":
            return "unhealthy"
        return state
