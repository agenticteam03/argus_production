"""Capability contract (v1.8 §12.3, lab: safety_class OP-003, provenance G-003)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal

from pydantic import BaseModel

from argus.domain.model import TargetInfo, TargetRef


class ExecutorError(Exception):
    def __init__(self, category: str, detail: str):
        super().__init__(detail)
        self.category = category
        self.detail = detail


@dataclass
class CapabilityResult:
    """What an implementation returns; the dispatcher turns it into an Observation."""
    values: dict[str, Any]
    model_text: str
    status: Literal["ok", "error"] = "ok"
    error_category: str = "none"
    source_time: datetime | None = None
    units: dict[str, str] = field(default_factory=dict)
    partial: bool = False
    coverage: str | None = None
    identities: dict[str, str] = field(default_factory=dict)


Impl = Callable[[BaseModel, TargetRef, TargetInfo | None, Any], CapabilityResult]


@dataclass(frozen=True)
class CapabilitySpec:
    name: str                          # canonical, e.g. "container.status"
    model_name: str                    # roadmap name shown to the model, e.g. "get_container_status"
    description: str
    use_when: str
    args_model: type[BaseModel]
    target_kinds: frozenset[str]
    level: int
    safety_class: Literal["READ_ONLY_SAFE", "READ_ONLY_SENSITIVE"]
    tags: frozenset[str]
    executor: str                      # "docker_read" | "host_probe" | "network_probe" | "db_probe" | "prometheus" | ...
    impl: Impl
    runs_in: Literal["tools_child", "worker"] = "tools_child"
    timeout_s: float = 10.0
    max_output_bytes: int = 8192
    permission: Literal["read"] = "read"
