"""Run events: telemetry of the real v1.8 graph nodes as they execute (v1.8 §10.1, §18.1).

Not audit: run events may be dropped without affecting safety. They exist so humans (formatted view)
and developers (raw view) can follow the agent loop. Node names are exactly the v1.8 graph nodes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel

V18_NODES = ("detect", "evidence_pack", "recall", "investigate", "act", "propose_action", "request_approval",
             "await_approval", "precheck_action", "execute_write", "verify", "record")


class RunEvent(BaseModel):
    incident_id: str
    seq: int
    at: datetime
    node: Literal["detect", "evidence_pack", "recall", "investigate", "act", "propose_action",
                  "request_approval", "await_approval", "precheck_action", "execute_write", "verify", "record"]
    phase: Literal["enter", "step", "exit"]
    data: dict[str, Any] = {}


class RunEventSink(Protocol):
    def append_run_event(self, incident_id: str, node: str, phase: str, data: dict[str, Any]) -> None: ...


class NullSink:
    def append_run_event(self, incident_id: str, node: str, phase: str, data: dict[str, Any]) -> None:
        return None
