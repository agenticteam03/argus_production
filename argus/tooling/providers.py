"""Tool providers behind the `ToolCatalogue` (ARCHITECTURE §12.5; T-0021).

`McpCatalogue` aggregates the two providers of the architecture: target-side reads (`runs_in="tools_child"`) go to
the MCP tools process (`McpChildProvider`), Argus-internal reads (`runs_in="worker"`, e.g. `knowledge.runbook`) run
in the worker (`InWorkerProvider`, the dispatcher). The registry stays the single source of truth; the providers only
decide where a capability runs. No MCP SDK type is used here (rule 10).
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel

from argus.capabilities.spec import CapabilitySpec
from argus.domain.model import Observation, TargetRef, utcnow
from argus.tooling.dispatch import Dispatcher, DirectProvider


class McpCatalogue(DirectProvider):
    def __init__(self, specs: list[CapabilitySpec], in_worker: Dispatcher, tools):
        super().__init__(specs, in_worker)
        self.tools = tools                  # McpToolsClient (or anything with .call(name, target, args))

    def call(self, spec: CapabilitySpec, args: BaseModel, target: TargetRef) -> Observation:
        if spec.runs_in == "worker":
            return self.dispatcher.call(spec, args, target)
        from argus.tooling.mcp.client import ToolsUnavailable
        base = dict(observation_id=f"obs_{uuid.uuid4().hex[:16]}", capability=spec.name, target=target,
                    host=target.host, executor=spec.executor, collected_at=utcnow())
        try:
            res = self.tools.call(spec.name, str(target), args.model_dump(mode="json"))
        except ToolsUnavailable as e:
            return Observation(**base, status="error", error_category="upstream_error",
                               model_text=f"{spec.name} on {target}: the tools process did not answer ({e})")
        if isinstance(res, Observation):
            return res
        return Observation(**base, status="refused", error_category=res.error_category,
                           model_text=f"{spec.name} on {target}: refused by the tools process ({res.detail})")
