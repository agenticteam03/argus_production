"""Synchronous MCP client for the tools process (ARCHITECTURE §12.5; T-0021).

The worker is synchronous; MCP is async. One background thread runs an event loop with ONE long-lived session task
(MCP/anyio contexts must be entered and left in the same task); calls are queued to it and wait for their answer.
`server` is an in-process `Server` (tests) or `StdioServerParameters` (the real child process). A call that fails in
the transport (the child died) ends the session: that call becomes `ToolsUnavailable`, the next one starts a new child.
A call with no answer within `timeout_s` (the child hangs) ends the session the same way, so later calls never queue
behind the stuck one.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from dataclasses import dataclass
from typing import Any

from mcp import Client

from argus.domain.model import Observation


class ToolsUnavailable(Exception):
    """The tools process cannot answer (not started, dead, or timed out)."""


@dataclass
class Refusal:
    """The tools server refused before executing anything."""
    error_category: str
    detail: str
    status: str = "refused"


class McpToolsClient:
    def __init__(self, server: Any, timeout_s: float = 30.0):
        self._server, self.timeout_s = server, timeout_s
        self.calls = 0
        self._closed = False
        self._broken = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._queue: asyncio.Queue | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # --- lifecycle -------------------------------------------------------------------------------
    def _ensure(self) -> None:
        with self._lock:
            if self._closed:
                raise ToolsUnavailable("the tools client is closed")
            if self._thread is not None and self._thread.is_alive() and self._error is None and not self._broken:
                return
            if self._thread is not None:
                self._thread.join(self.timeout_s)          # let a broken session finish closing its child
            self._ready.clear()
            self._error, self._broken = None, False
            self._thread = threading.Thread(target=self._run, name="argus-mcp-client", daemon=True)
            self._thread.start()
        if not self._ready.wait(self.timeout_s) or self._error is not None:
            raise ToolsUnavailable(f"tools server did not start: {self._error!r}")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            self._task = loop.create_task(self._session())
            loop.run_until_complete(self._task)
        except BaseException as e:            # noqa: BLE001 - reported to the callers, never raised in the thread
            self._error = e
        finally:
            self._ready.set()
            loop.close()

    async def _session(self) -> None:
        self._queue = asyncio.Queue()
        async with Client(self._server) as client:
            self._ready.set()
            while True:
                job = await self._queue.get()
                if job is None:
                    return
                fn, fut = job
                try:
                    fut.set_result(await fn(client))
                except Exception as e:        # noqa: BLE001 - the transport failed: answer, then end the session
                    self._broken = True
                    fut.set_result(e)
                    return

    def _submit(self, fn) -> Any:
        self._ensure()
        loop = self._loop
        cf = asyncio.run_coroutine_threadsafe(self._enqueue(fn), loop)
        try:
            result = cf.result(self.timeout_s)
        except Exception as e:                 # timeout or loop gone
            self._abandon()
            raise ToolsUnavailable(f"no answer from the tools server: {e!r}") from e
        if isinstance(result, BaseException):
            raise ToolsUnavailable(f"tools server error: {result!r}") from result
        return result

    def _abandon(self) -> None:
        """No answer in time: end this session (closing its child), so the next call starts a new one."""
        with self._lock:
            self._broken = True
            loop, task = self._loop, self._task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:               # the loop is already closed
                pass

    async def _enqueue(self, fn):
        fut = asyncio.get_running_loop().create_future()
        await self._queue.put((fn, fut))
        return await fut

    def close(self) -> None:
        with self._lock:
            self._closed = True
            loop, thread = self._loop, self._thread
            if thread is None or not thread.is_alive() or loop is None:
                self._thread = None
                return
            asyncio.run_coroutine_threadsafe(self._queue.put(None), loop)
            self._thread = None
        thread.join(self.timeout_s)

    # --- calls -----------------------------------------------------------------------------------
    def list_names(self) -> set[str]:
        res = self._submit(lambda c: c.list_tools())
        return {t.name for t in res.tools}

    def call(self, name: str, target: str, args: dict[str, Any]) -> Observation | Refusal:
        self.calls += 1
        res = self._submit(lambda c: c.call_tool(name, {"target": target, "args": args}))
        text = res.content[0].text if res.content else ""
        if res.is_error:
            try:
                body = json.loads(text)
                return Refusal(body["error_category"], body.get("detail", ""))
            except (ValueError, KeyError):
                return Refusal("forbidden", text or "refused by the tools server")
        return Observation.model_validate_json(text)


def child_client(env: dict[str, str], command: list[str] | None = None, timeout_s: float = 30.0) -> McpToolsClient:
    """The real tools process over stdio. `command` is the whole command line (in the image: the sudo launcher that
    starts the tools server as `argus-tools`, §12.6); `None` = this interpreter with `-m argus.tooling.mcp.tools_server`.
    `env` names the config and the secrets folder (MCP passes only a minimal environment otherwise)."""
    from mcp.client.stdio import StdioServerParameters
    cmd = command or [sys.executable, "-m", "argus.tooling.mcp.tools_server"]
    params = StdioServerParameters(command=cmd[0], args=cmd[1:], env=env)
    return McpToolsClient(params, timeout_s)
