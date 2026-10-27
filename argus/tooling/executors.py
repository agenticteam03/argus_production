"""Executor clients and the ExecutorRegistry (v1.8 §12.3).

An executor is a *kind* of backend. The target's host selects the instance through the inventory;
credentials come from settings keyed by (host, executor). Nothing here is persisted.
"""
from __future__ import annotations

import re
import time
from string import Template
from typing import Callable

import httpx

from argus.capabilities.spec import ExecutorError
from argus.domain.model import TargetRef


class TargetAgentClient:
    """docker_read / host_probe / network_probe / db_probe: one target-agent prefix per executor, one token each."""

    def __init__(self, base_url: str, token: str | None, timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_s = timeout_s

    def get(self, path: str, params: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = httpx.get(self.base_url + path, params=params, headers=headers, timeout=self.timeout_s)
        except httpx.TimeoutException as e:
            raise ExecutorError("timeout", f"{self.base_url}{path}: timeout") from e
        except httpx.HTTPError as e:
            raise ExecutorError("unreachable", f"{self.base_url}{path}: {type(e).__name__}") from e
        if r.status_code in (401, 403):
            raise ExecutorError("forbidden", f"{path}: HTTP {r.status_code} {r.text[:200]}")
        if r.status_code == 404:
            raise ExecutorError("not_found", f"{path}: not found or not in the host's allowlist")
        if r.status_code == 400:
            raise ExecutorError("invalid_args", f"{path}: {r.text[:200]}")
        if r.status_code >= 300:
            raise ExecutorError("upstream_error", f"{path}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()


_MOUNT = re.compile(r"/[A-Za-z0-9_/-]*")          # as the inventory checks a mount (T-0024)


class PrometheusClient:
    """prometheus executor: only named signal templates (never free-form PromQL)."""

    def __init__(self, base_url: str, token: str | None, signals: dict[str, str], timeout_s: float = 10.0,
                 lines: dict[str, tuple[float, str]] | None = None,
                 class_signals: dict[str, list[tuple[str, str]]] | None = None):
        """`lines` and `class_signals` (T-0047 H5, `analysis.anomaly_summary`): the warning line and direction per
        signal (`signals.yaml` `thresholds:`) and the (signal, scope) list per class (`ui-incident-signals.yaml`)."""
        self.base_url = base_url.rstrip("/")
        self.signals = signals
        self.timeout_s = timeout_s
        self.lines, self.class_signals = lines or {}, class_signals or {}

    def expr(self, signal: str, target: TargetRef, mounts: str = "") -> str:
        """`mounts` (T-0036): the target's declared mounts joined by `|` (a PromQL regex), plain paths only, as the
        inventory validates them; anything else is refused."""
        if signal not in self.signals:
            raise ExecutorError("invalid_args", f"unknown signal {signal!r}")
        if mounts and not all(_MOUNT.fullmatch(m) for m in mounts.split("|")):
            raise ExecutorError("invalid_args", "mounts must be plain absolute paths")
        return Template(self.signals[signal]).substitute(host=target.host, name=target.name, mounts=mounts)

    def range(self, signal: str, target: TargetRef, minutes: int, step_s: int,
              mounts: str = "", end_offset_s: int = 0) -> list[tuple[float, float]]:
        """`end_offset_s` (T-0038): the window ends that many seconds ago (an earlier window, same length)."""
        end = time.time() - max(0, int(end_offset_s))
        try:
            r = httpx.get(f"{self.base_url}/api/v1/query_range",
                          params={"query": self.expr(signal, target, mounts), "start": end - minutes * 60, "end": end,
                                  "step": step_s}, timeout=self.timeout_s)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ExecutorError("unreachable", f"prometheus: {type(e).__name__}") from e
        result = r.json().get("data", {}).get("result", [])
        if not result:
            return []
        return [(float(t), float(v)) for t, v in result[0]["values"]]


class KnowledgeClient:
    """argus_internal executor (in-worker, ARCHITECTURE §10.5): reads the runbook library through the KnowledgePort,
    and earlier closed incidents through the IncidentMemoryPort (T-0039). No network, no token. A query with no
    matching words still returns the runbook's working sections."""

    FALLBACK_QUERY = "diagnostic workflow decision tree evidence interpretation"

    def __init__(self, knowledge, memory=None, inventory=None, metrics=None, reference=None):
        self.knowledge, self.memory = knowledge, memory
        self.inventory, self.metrics = inventory, metrics     # T-0046 L4: `network.link_states`
        self._reference = reference                           # T-0056 (ACR-0034): the installed reference corpus

    def reference(self, query: str, k: int) -> list[dict]:
        """ACR-0034: passages of the installed reference corpus (keyword, or hybrid with keyword fallback)."""
        if self._reference is None:
            raise ExecutorError("unreachable", "no reference corpus installed in this process")
        return self._reference.search(query, k)

    def link_history(self, ref: str, start, end) -> list[dict]:
        """T-0046 L4: the recorded transitions of the links `ref` owns or is the dependency of (`link_event`)."""
        if self.memory is None or not hasattr(self.memory, "link_events"):
            raise ExecutorError("unreachable", "no link record in this process")
        return self.memory.link_events(ref, start, end)

    def latest_links(self) -> dict:
        """T-0046 L4: the last recorded transition of every link, by (owner, dependency)."""
        read = getattr(self.memory, "latest_link_events", None)
        return read() if read else {}

    def current_links(self, owners: list[TargetRef]) -> tuple[list[tuple], set[str]]:
        """T-0046 L4: the links of `owners` as the recorder judges them now, from each owner's own host's probes
        (`application/link_transitions.read_links`); ([], set()) when this process has no inventory or metrics."""
        if self.inventory is None or self.metrics is None:
            return [], set()
        from argus.application.link_transitions import read_links
        infos = [i for i in (self.inventory.target(o) for o in owners) if i is not None]
        return read_links(self.inventory, self.metrics, infos)

    def prior_incidents(self, target: TargetRef, incident_class: str, k: int) -> list:
        """Closed incidents of this target and class, newest first (`similar_incidents`)."""
        if self.memory is None:
            raise ExecutorError("unreachable", "no incident memory in this process")
        return self.memory.similar_incidents(target, incident_class, k)

    def runbook(self, runbook_id: str, query: str, k: int = 3) -> list:
        if runbook_id not in getattr(self.knowledge, "ids", set()):
            raise ExecutorError("not_found", f"runbook {runbook_id} is not in the library")
        return (self.knowledge.search(query, k, [runbook_id])
                or self.knowledge.search(self.FALLBACK_QUERY, k, [runbook_id]))


ClientFactory = Callable[[str, str | None], object]


class ExecutorRegistry:
    def __init__(self):
        self._factories: dict[str, ClientFactory] = {}

    def register(self, name: str, factory: ClientFactory) -> None:
        self._factories[name] = factory

    def names(self) -> set[str]:
        return set(self._factories)

    def client(self, name: str, url: str, token: str | None):
        if name not in self._factories:
            raise ExecutorError("internal", f"executor {name!r} has no client")
        return self._factories[name](url, token)
