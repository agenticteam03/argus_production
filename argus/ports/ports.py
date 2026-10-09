"""The seven deterministic outbound ports (architecture v1.8 §8.1). Protocols and value types only."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from argus.domain.model import (AlertNotification, AuditRecord, EvidenceRecord, HostInfo, Incident, MetricSnapshot,
                                Passage, TargetInfo, TargetRef)


class StaleMetrics(Exception):
    """The newest sample is older than the staleness limit, or no sample exists."""


class MetricsUnavailable(Exception):
    """The metrics backend could not be reached."""


class AlertsUnavailable(Exception):
    """A host's Alertmanager could not be read (ACR-0003)."""


class AlertSourcePort(Protocol):
    def firing_alerts(self, host: str) -> list[AlertNotification]: ...   # only alerts labelled with that host


class MetricsPort(Protocol):
    def snapshot(self, target: TargetRef, signals: set[str]) -> MetricSnapshot: ...
    def range(self, target: TargetRef, signal: str, minutes: int, step_s: int) -> list[tuple[float, float]]: ...


# --- LLM (provider-neutral) ------------------------------------------------------------------
class ModelToolDefinition(BaseModel):
    name: str
    description: str
    parameters_schema: dict


class ModelToolCall(BaseModel):
    name: str
    arguments_json: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ModelReply(BaseModel):
    text: str | None
    tool_calls: list[ModelToolCall]
    finish_reason: Literal["stop", "tool_calls", "length", "content_filter", "error"]
    usage: Usage = Usage()


class ModelMessage(BaseModel):
    role: Literal["system", "user"]
    content: str


class LLMPort(Protocol):
    def decide(self, messages: list[ModelMessage], tools: list[ModelToolDefinition]) -> ModelReply: ...


class KnowledgePort(Protocol):
    def search(self, query: str, k: int, runbook_ids: list[str] | None = None) -> list[Passage]: ...


class IncidentMemoryPort(Protocol):
    def create_incident(self, incident: Incident, idempotency_key: str | None) -> tuple[Incident, bool]: ...
    def get_incident(self, incident_id: str) -> Incident | None: ...
    def update_incident(self, incident: Incident) -> None: ...
    def list_incidents(self, limit: int = 50) -> list[Incident]: ...
    def claim_next_queued(self, worker_id: str = "local", lease_s: int = 300) -> Incident | None: ...
    def renew_claim(self, incident_id: str, worker_id: str, lease_s: int = 300,
                    now: datetime | None = None) -> bool: ...
    def requeue_expired(self, now: datetime | None = None) -> int: ...
    def active_incident(self, target: TargetRef) -> Incident | None: ...
    def append_evidence(self, record: EvidenceRecord) -> None: ...
    def get_evidence(self, evidence_ids: list[str]) -> list[EvidenceRecord]: ...
    def list_evidence(self, incident_id: str) -> list[EvidenceRecord]: ...
    def similar_incidents(self, target: TargetRef, incident_class: str, k: int) -> list[Incident]: ...


class AuditSinkPort(Protocol):
    def append(self, record: AuditRecord) -> None: ...
    def list_for(self, incident_id: str) -> list[AuditRecord]: ...


class NotificationPort(Protocol):
    def notify(self, key: str, payload: dict[str, Any]) -> None: ...


class InventoryPort(Protocol):
    def hosts(self) -> list[HostInfo]: ...
    def host(self, name: str) -> HostInfo | None: ...
    def target(self, ref: TargetRef) -> TargetInfo | None: ...
    def targets(self, host: str | None = None) -> list[TargetInfo]: ...
    def neighbours(self, ref: TargetRef) -> list[TargetRef]: ...
    def version(self) -> str: ...
