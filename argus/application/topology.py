"""ACR-0017: the system map for the UI (`GET /api/v1/topology[?incident_id=<id>]`).

Built from what Argus already holds, with no new read on the hosts:
- the inventory: targets, declared dependencies with their ports, declared networks;
- the latest named signals per container (`restarts_10m`, `health_unhealthy`) and the dependency probe
  (`dependency_probe_min`) through the MetricsPort;
- with an incident, its stored `container.status` evidence for its target and root cause (their real state and
  networks at the time of the incident).

Shown on purpose: container names, Docker networks, dependency ports. Never: VM addresses, Argus's internal endpoints
(executor and Alertmanager URLs), tokens or secrets. A value Argus does not know is `unknown`, never ok.
"""
from __future__ import annotations

import copy
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from argus.domain.model import EvidenceRecord, Incident, TargetRef
from argus.ports.ports import MetricsUnavailable, StaleMetrics

CONTAINER_SIGNALS = {"restarts_10m", "health_unhealthy", "dependency_probe_min"}
HOST_SIGNALS = {"host_cpu_busy_ratio"}
STATES = ("running", "restarting", "unhealthy", "stopped", "unknown")
DOCKER_STATE = {"running": "running", "restarting": "restarting", "exited": "stopped", "dead": "stopped",
                "created": "stopped", "paused": "stopped"}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _mib(value: Any) -> str | None:
    return f"{round(value / 1048576)} MiB" if isinstance(value, (int, float)) and value > 0 else None


class Topology:
    def __init__(self, inventory, metrics, store, home_host: str | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 clock: Callable[[], float] = time.monotonic, ttl_s: float = 20, ttl_closed_s: float = 600):
        self.inventory, self.metrics, self.store = inventory, metrics, store
        self.home_host = home_host or None
        self.now, self.clock, self.ttl_s, self.ttl_closed_s = now, clock, ttl_s, ttl_closed_s
        self._global: tuple[float, dict] | None = None
        self._overlays: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    # --- the global map (shared by every viewer for ttl_s) ------------------------------------------------------
    def view(self) -> dict:
        with self._lock:
            if self._global and self._global[0] > self.clock():
                return self._global[1]
        answer = self._build()
        with self._lock:
            self._global = (self.clock() + self.ttl_s, answer)
        return answer

    def _build(self) -> dict:
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
            nodes.append({"id": ref, "host": t.ref.host, "label": t.ref.name, "target": ref, "kind": t.ref.kind,
                          "sub": "host" if t.ref.kind == "host" else ("database container" if t.database else "container"),
                          "status": self._status(t.ref, vals), "info": info})
            probe = vals.get("dependency_probe_min")
            for dep in t.depends_on:
                d = str(dep)
                port = ports.get(d, [None])[0] if ports.get(d) else None
                single = len(t.depends_on) == 1
                if t.ref.kind != "container" or dep.kind != "container" or port is None or probe is None:
                    state = "unknown"
                elif probe >= 1:
                    state = "ok"
                else:
                    state = "broken" if single else "unknown"   # several dependencies: the probe's minimum names none
                label = (f"tcp {port}" if port else "declared dependency") + (" · not reachable" if state == "broken" else "")
                edges.append({"from": ref, "to": d, "port": port, "state": state, "label": label})
        if self.home_host in hosts:
            for h in hosts:
                if h != self.home_host:
                    edges.append({"from": f"{self.home_host}/host:{self.home_host}", "to": f"{h}/host:{h}",
                                  "port": None, "state": "read", "label": "Argus reads"})
        return {"observed_at": _iso(self.now()),
                "hosts": [{"id": h, "label": h, "role": "argus" if h == self.home_host else "monitored"} for h in hosts],
                "nodes": nodes, "edges": edges}

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
        answer = self._overlay(inc, copy.deepcopy(self.view()))
        with self._lock:
            self._overlays[inc.id] = (self.clock() + (self.ttl_closed_s if inc.closed_at else self.ttl_s), answer)
            if len(self._overlays) > 200:
                now = self.clock()
                self._overlays = {k: v for k, v in self._overlays.items() if v[0] > now}
        return answer

    def _overlay(self, inc: Incident, body: dict) -> dict:
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
        for edge in body["edges"]:
            a, b = nets.get(edge["from"]), nets.get(edge["to"])
            if a is not None and b is not None and not set(a) & set(b):
                edge["state"] = "broken"
                edge["label"] = (f"tcp {edge['port']} · " if edge.get("port") else "") + "no shared network"
        return body

    @staticmethod
    def _docker_status(data: dict) -> str:
        state = DOCKER_STATE.get(str(data.get("state") or "").lower(), "unknown")
        if state == "running" and str(data.get("health") or "").lower() == "unhealthy":
            return "unhealthy"
        return state
