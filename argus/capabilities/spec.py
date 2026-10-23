"""Capability contract (v1.8 §12.3, safety classes ACR-0026, provenance G-003)."""
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

# §12.3 (ACR-0026): the five safety classes. This release registers only the two read classes; the MUTATING ones come
# with the write contract (§14.8), and FORBIDDEN is never registered (it exists so that risk.yaml and runbooks name it).
SAFETY_CLASSES = ("READ_ONLY_SAFE", "READ_ONLY_SENSITIVE", "MUTATING_LOW_RISK", "MUTATING_HIGH_RISK", "FORBIDDEN")


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
    # §12.7 (T-0034): > 0 = a combined capability: its impl gets an invoker bound to InvokeCapability (not an executor
    # client) and may make at most this many sub-reads, each validated, budgeted, policy-checked, audited and stored
    max_subcalls: int = 0
    # ACR-0028 (G-006): the value paths this read may keep ("a", "a[].b", "a.b"); the rest is dropped before redaction
    # and storage. Required for a READ_ONLY_SENSITIVE read; None = not minimized (a safe read, for now).
    allowed_fields: frozenset[str] | None = None
