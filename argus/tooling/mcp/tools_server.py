"""The MCP tools server: target-side reads in their own process (ARCHITECTURE §12.5, §12.6; T-0021).

stdio only (no network listener). It publishes the `runs_in="tools_child"` capabilities, re-checks the name, the
static deployment scope and the argument shape, then delegates to `dispatch.py` (redaction, size limit, attribution
guard). An executed read answers an `Observation` as JSON; a refusal answers `is_error` with its category. Policy,
audit and evidence stay in the worker.

    python -m argus.tooling.mcp.tools_server      (started by the worker, never by hand)
"""
from __future__ import annotations

import json
from typing import Any

import mcp_types as types
from mcp.server import Server
from pydantic import ValidationError

from argus.capabilities.spec import CapabilitySpec
from argus.domain.model import Observation, TargetRef
from argus.ports.ports import InventoryPort
from argus.tooling.dispatch import Dispatcher

NAME = "argus-tools"


class Refused(Exception):
    def __init__(self, category: str, detail: str):
        super().__init__(detail)
        self.category, self.detail = category, detail


def _schema(spec: CapabilitySpec) -> dict[str, Any]:
    return {"type": "object", "required": ["target", "args"],
            "properties": {"target": {"type": "string", "description": "inventory target, e.g. vm-166/container:x"},
                           "args": spec.args_model.model_json_schema()}}


def handle(published: dict[str, CapabilitySpec], dispatcher: Dispatcher, inventory: InventoryPort,
           name: str, arguments: dict[str, Any] | None) -> Observation:
    """One call, synchronous and transport-free. Raises `Refused` before anything is executed."""
    spec = published.get(name)
    if spec is None:
        raise Refused("forbidden", f"{name} is not a published read capability")
    arguments = arguments or {}
    try:
        target = TargetRef.parse(str(arguments.get("target")))
    except ValueError as e:
        raise Refused("invalid_args", f"bad target: {e}")
    if target.kind not in spec.target_kinds or inventory.target(target) is None:
        raise Refused("out_of_scope", f"{target} is not in the deployment inventory")
    try:
        args = spec.args_model.model_validate(arguments.get("args") or {})
    except ValidationError as e:
        raise Refused("invalid_args", str(e.errors()[0]["msg"]))
    return dispatcher.call(spec, args, target)


def build_server(specs: list[CapabilitySpec], dispatcher: Dispatcher, inventory: InventoryPort) -> Server:
    published = {s.name: s for s in specs if s.runs_in == "tools_child" and s.permission == "read"}
    tools = [types.Tool(name=s.name, description=s.description, input_schema=_schema(s)) for s in published.values()]

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            obs = handle(published, dispatcher, inventory, params.name, params.arguments)
        except Refused as r:
            body = json.dumps({"error_category": r.category, "detail": r.detail})
            return types.CallToolResult(content=[types.TextContent(type="text", text=body)], is_error=True)
        return types.CallToolResult(content=[types.TextContent(type="text", text=obs.model_dump_json())],
                                    is_error=False)

    return Server(NAME, on_list_tools=on_list_tools, on_call_tool=on_call_tool)


def main() -> None:
    import anyio
    from mcp.server.stdio import stdio_server

    from argus.infrastructure.wiring import Settings, tools_dispatcher
    specs, dispatcher, inventory = tools_dispatcher(Settings())
    server = build_server(specs, dispatcher, inventory)

    async def run():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    anyio.run(run)


if __name__ == "__main__":
    main()
