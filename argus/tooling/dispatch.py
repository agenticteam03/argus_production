"""Dispatcher with executor resolution and the DirectProvider catalogue (v1.8 §12.3, §12.5; lab §4)."""
from __future__ import annotations

import json
import time
import uuid
from typing import Callable

from pydantic import BaseModel

from argus.capabilities.redaction import Redactor
from argus.capabilities.spec import CapabilitySpec, ExecutorError
from argus.domain.model import Observation, TargetRef, utcnow
from argus.ports.ports import InventoryPort
from argus.tooling.executors import ExecutorRegistry


class Dispatcher:
    def __init__(self, inventory: InventoryPort, executors: ExecutorRegistry,
                 credentials: dict[tuple[str, str], str], redactor: Redactor,
                 reload: Callable[[str, str], str | None] | None = None):
        self.inventory = inventory
        self.executors = executors
        self.credentials = credentials
        self.redactor = redactor
        # T-0033: re-reads one executor token from its file (the deployment's copy) when the executor rejects it
        self.reload = reload

    def _execute(self, spec: CapabilitySpec, args: BaseModel, target: TargetRef, url: str):
        key = (target.host, spec.executor)
        try:
            return spec.impl(args, target, self.inventory.target(target),
                             self.executors.client(spec.executor, url, self.credentials.get(key)))
        except ExecutorError as e:
            fresh = self.reload(*key) if self.reload and e.category == "forbidden" else None
            if not fresh or fresh == self.credentials.get(key):
                raise
        # T-0033: the token was rotated (the file changed since it was read): keep the new one, retry ONCE
        self.credentials[key] = fresh
        return spec.impl(args, target, self.inventory.target(target), self.executors.client(spec.executor, url, fresh))

    def call(self, spec: CapabilitySpec, args: BaseModel, target: TargetRef) -> Observation:
        started = time.monotonic()
        base = dict(observation_id=f"obs_{uuid.uuid4().hex[:16]}", capability=spec.name, target=target,
                    host=target.host, executor=spec.executor, collected_at=utcnow())
        host = self.inventory.host(target.host)
        url = "in-worker" if spec.runs_in == "worker" else (host.executors.get(spec.executor) if host else None)
        if not url:
            # Never fall back to another host (v1.8 §4.6, §12.3).
            return Observation(**base, status="refused", error_category="not_found",
                               model_text=f"{spec.name}: executor {spec.executor!r} is not available on {target.host}")
        try:
            res = self._execute(spec, args, target, url)
        except ExecutorError as e:
            status = "timeout" if e.category == "timeout" else "error"
            return Observation(**base, status=status, error_category=e.category,
                               duration_ms=int((time.monotonic() - started) * 1000),
                               model_text=f"{spec.name} on {target}: {status} ({e.category}): {e.detail}")
        echoed = res.values.get("host") if isinstance(res.values, dict) else None
        if echoed is not None and echoed != target.host:
            # Evidence attribution guard: an answer from another host must never become this target's evidence.
            return Observation(**base, status="error", error_category="upstream_error",
                               duration_ms=int((time.monotonic() - started) * 1000),
                               model_text=f"{spec.name} on {target}: ATTRIBUTION MISMATCH — answer came from {echoed!r}")
        values, n1 = self.redactor.value(res.values)
        text, n2 = self.redactor.text(res.model_text)
        raw = json.dumps(values, default=str)
        truncated = False
        if len(raw) > spec.max_output_bytes:
            truncated = True
            values = {"truncated_json": raw[: spec.max_output_bytes]}
        return Observation(**base, status=res.status, error_category=res.error_category,
                           duration_ms=int((time.monotonic() - started) * 1000), values=values,
                           units=res.units, source_time=res.source_time, partial=res.partial,
                           coverage=res.coverage, identities=res.identities, truncated=truncated,
                           redactions=n1 + n2, model_text=text)


class DirectProvider:
    """ToolCatalogue implementation that calls the registry in-process (lab: no MCP child)."""

    def __init__(self, specs: list[CapabilitySpec], dispatcher: Dispatcher):
        self._specs = {s.name: s for s in specs}
        self._by_model_name = {s.model_name: s for s in specs}
        self.dispatcher = dispatcher

    def list(self) -> list[CapabilitySpec]:
        return list(self._specs.values())

    def spec(self, name: str) -> CapabilitySpec | None:
        return self._specs.get(name) or self._by_model_name.get(name)

    def call(self, spec: CapabilitySpec, args: BaseModel, target: TargetRef) -> Observation:
        return self.dispatcher.call(spec, args, target)
