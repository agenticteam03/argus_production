"""The seven deterministic outbound ports (architecture v1.8 §8.1). Protocols and value types only."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, NamedTuple, Protocol

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
    # every active alert of that host, silenced and inhibited included: what is absent is resolved (ACR-0005)
    def active_alerts(self, host: str) -> list[AlertNotification]: ...


class ProbeSample(NamedTuple):
    """One dependency probe of an owner (ACR-0021): success 1 / 0 (None = missing or stale), the answer time in seconds
    (None = unknown), the sample time, and why it failed (T-0045 B8: refused, timeout, dns, other; None = not said)."""
    success: float | None
    duration_s: float | None
    at: datetime
    error_kind: str | None = None


class MetricsPort(Protocol):
    def snapshot(self, target: TargetRef, signals: set[str]) -> MetricSnapshot: ...
    # `end` (ACR-0017): the window ends then (None = now); an incident's chart ends at its close, not today
    def range(self, target: TargetRef, signal: str, minutes: int, step_s: int,
              end: datetime | None = None) -> list[tuple[float, float]]: ...
    # ACR-0021: the owner's probes, one per declared dependency (by the dependency's container name); {} = none known
    def dependency_probes(self, target: TargetRef) -> dict[str, ProbeSample]: ...
    # T-0046: every distinct probe sample in (start, end], oldest first, keyed by dependency name.
    def dependency_probe_history(self, target: TargetRef, start: datetime,
                                 end: datetime) -> dict[str, list[ProbeSample]]: ...


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
    # ACR-0041: an escalated incident becomes closed with a person's resolution; None when it is not escalated (any more)
    def resolve_incident(self, incident_id: str, by: str, reason: str, at: datetime) -> Incident | None: ...
    # `parent_id` (ACR-0021): only the re-checks of that incident, newest first
    def list_incidents(self, limit: int = 50, parent_id: str | None = None) -> list[Incident]: ...
    def claim_next_queued(self, worker_id: str = "local", lease_s: int = 300) -> Incident | None: ...
    def renew_claim(self, incident_id: str, worker_id: str, lease_s: int = 300,
                    now: datetime | None = None) -> bool: ...
    # inc_6a4980a4d8ed: a run paused at an interrupt is parked (no worker holds it) until its approval is answered
    # (the answer requeues it) or expires; wake_answered requeues it when the answer came before the park
    def park_claim(self, incident_id: str, worker_id: str, approval_id: str | None, lease_s: int = 300) -> bool: ...
    def wake_answered(self, incident_id: str, approval_id: str) -> bool: ...
    def requeue_expired(self, now: datetime | None = None) -> int: ...
    def active_incident(self, target: TargetRef) -> Incident | None: ...
    def append_evidence(self, record: EvidenceRecord) -> None: ...
    def get_evidence(self, evidence_ids: list[str]) -> list[EvidenceRecord]: ...
    def list_evidence(self, incident_id: str) -> list[EvidenceRecord]: ...
    def similar_incidents(self, target: TargetRef, incident_class: str, k: int) -> list[Incident]: ...
    # T-0046: per-link durable cursor and atomic sample/event/audit recording.
    def link_probe_cursors(self, owner: str) -> dict[str, dict[str, Any]]: ...
    def record_link_probe(self, owner: str, dependency: str, state: str, latency_ms: float | None,
                          reason: str | None, at: datetime) -> bool: ...


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
