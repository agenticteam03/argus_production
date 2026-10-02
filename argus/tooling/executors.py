"""Executor clients and the ExecutorRegistry (v1.8 §12.3).

An executor is a *kind* of backend. The target's host selects the instance through the inventory;
credentials come from settings keyed by (host, executor). Nothing here is persisted.
"""
from __future__ import annotations

import time
from string import Template
from typing import Callable

import httpx

from argus.capabilities.spec import ExecutorError
from argus.domain.model import TargetRef


class TargetAgentClient:
    """docker_read / host_probe / network_probe: one target-agent prefix per executor, one token each."""

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


class PrometheusClient:
    """prometheus executor: only named signal templates (never free-form PromQL)."""

    def __init__(self, base_url: str, token: str | None, signals: dict[str, str], timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.signals = signals
        self.timeout_s = timeout_s

    def expr(self, signal: str, target: TargetRef) -> str:
        if signal not in self.signals:
            raise ExecutorError("invalid_args", f"unknown signal {signal!r}")
        return Template(self.signals[signal]).substitute(host=target.host, name=target.name)

    def range(self, signal: str, target: TargetRef, minutes: int, step_s: int) -> list[tuple[float, float]]:
        end = time.time()
        try:
            r = httpx.get(f"{self.base_url}/api/v1/query_range",
                          params={"query": self.expr(signal, target), "start": end - minutes * 60, "end": end,
                                  "step": step_s}, timeout=self.timeout_s)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ExecutorError("unreachable", f"prometheus: {type(e).__name__}") from e
        result = r.json().get("data", {}).get("result", [])
        if not result:
            return []
        return [(float(t), float(v)) for t, v in result[0]["values"]]


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
