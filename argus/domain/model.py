"""Domain vocabulary of Argus v1.8-lab (architecture v1.8 §5 + lab additions G-003, G-007, OP-003).

Framework-free: only Pydantic value models. No I/O.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JsonValue = Any

# ---------------------------------------------------------------------------------------------
# Targets (§5.1): host is part of the identity. Kinds are a registry, not a closed Literal.
# ---------------------------------------------------------------------------------------------
TARGET_KINDS: set[str] = {"container", "host", "network_endpoint", "database", "service", "volume"}


class TargetRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    host: str
    kind: str
    name: str

    @classmethod
    def parse(cls, text: str) -> "TargetRef":
        """Parse 'host-t1/container:worker'. The host part is mandatory."""
        if "/" not in text or ":" not in text.split("/", 1)[1]:
            raise ValueError(f"target must look like 'host/kind:name', got {text!r}")
        host, rest = text.split("/", 1)
        kind, name = rest.split(":", 1)
        if not host or not name:
            raise ValueError(f"empty host or name in {text!r}")
        if kind not in TARGET_KINDS:
            raise ValueError(f"unknown target kind {kind!r}")
        return cls(host=host, kind=kind, name=name)

    def __str__(self) -> str:
        return f"{self.host}/{self.kind}:{self.name}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------
# Principals and triggers (§5.2)
# ---------------------------------------------------------------------------------------------
class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    kind: Literal["human", "service", "agent"]
    role: Literal["viewer", "operator", "approver", "service", "peer_agent"]
    scopes: frozenset[str] = frozenset()


class TriggerKind(StrEnum):
    alert = "alert"
    manual = "manual"
    scheduled = "scheduled"
    system = "system"
    peer = "peer"


class RequestKind(StrEnum):
    check = "check"      # "is it healthy?"  → healthy ends quietly
    report = "report"    # "there is a problem" → no matching class ⇒ unsupported_escalated


class IncidentStatus(StrEnum):
    queued = "queued"
    running = "running"
    closed = "closed"
    escalated = "escalated"


class IncidentOutcome(StrEnum):
    no_incident = "no_incident"
    undiagnosable = "undiagnosable"
    unsupported_escalated = "unsupported_escalated"
    diagnosed = "diagnosed"
    no_action_escalated = "no_action_escalated"
    refused = "refused"
    resolved_externally = "resolved_externally"     # every alert resolved before a run started (§6.4, T-0026)


class Incident(BaseModel):
    id: str
    target: TargetRef
    trigger_kind: TriggerKind
    request_kind: RequestKind
    reason: str
    principal: str | None
    trigger_id: str
    incident_class: str | None = None
    strategy: str | None = None
    status: IncidentStatus = IncidentStatus.queued
    outcome: IncidentOutcome | None = None
    diagnosis: str | None = None
    confidence: str | None = None
    root_cause_target: str | None = None
    findings: list[str] = []
    opened_at: datetime
    closed_at: datetime | None = None
    parent_id: str | None = None          # ACR-0021 (T-0045 B5): the incident this one re-checks; never changes


# ---------------------------------------------------------------------------------------------
# Evidence (§5.4 + G-003 provenance + G-007 unknown ≠ healthy)
# ---------------------------------------------------------------------------------------------
class Observation(BaseModel):
    observation_id: str
    status: Literal["ok", "error", "timeout", "refused"]
    capability: str
    target: TargetRef
    host: str
    executor: str
    source_time: datetime | None = None       # when the source measured (None = unknown)
    collected_at: datetime
    duration_ms: int = 0
    values: dict[str, JsonValue] = {}
    units: dict[str, str] = {}
    partial: bool = False
    coverage: str | None = None
    identities: dict[str, str] = {}
    error_category: Literal["none", "unreachable", "timeout", "not_found", "forbidden",
                            "invalid_args", "upstream_error", "internal", "out_of_scope",
                            "budget"] = "none"
    truncated: bool = False
    redactions: int = 0
    model_text: str


class EvidenceRecord(BaseModel):
    evidence_id: str
    incident_id: str
    kind: Literal["observation", "metric_snapshot", "alert", "reported_symptom"]
    capability: str | None
    target: str | None
    host: str | None
    executor: str | None
    caller: str
    source_time: datetime | None
    collected_at: datetime
    status: str
    values: dict[str, JsonValue]
    model_text: str
    partial: bool = False
    truncated: bool = False
    redactions: int = 0
    sha256: str = ""

    def with_hash(self) -> "EvidenceRecord":
        body = self.model_dump(mode="json", exclude={"sha256"})
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"sha256": digest})


class EvidenceRef(BaseModel):
    evidence_id: str
    sha256: str
    capability: str | None
    status: str
    model_text: str


class MetricSnapshot(BaseModel):
    target: TargetRef
    observed_at: datetime | None               # newest sample used; None = no sample at all
    values: dict[str, float | None]            # None = missing (G-007), never coerced to 0


class Passage(BaseModel):
    runbook_id: str
    runbook_version: str
    runbook_status: str
    section: str
    text: str
    score: float


# ---------------------------------------------------------------------------------------------
# Decisions (§5.5) — produced by every strategy
# ---------------------------------------------------------------------------------------------
class ReadCall(BaseModel):
    name: str
    arguments: dict[str, JsonValue]


class UseReadTools(BaseModel):
    kind: Literal["use_read_tools"] = "use_read_tools"
    calls: list[ReadCall]


class Conclude(BaseModel):
    kind: Literal["conclude"] = "conclude"
    diagnosis: str
    evidence_ids: list[str]
    confidence: Literal["low", "medium", "high"]
    root_cause_target: str | None = None


class Escalate(BaseModel):
    kind: Literal["escalate"] = "escalate"
    reason: str
    evidence_ids: list[str] = []


AgentDecision = Annotated[UseReadTools | Conclude | Escalate, Field(discriminator="kind")]


class InvalidDecision(BaseModel):
    kind: Literal["invalid"] = "invalid"
    reason: Literal["fabricated_tool", "malformed", "multiple_calls", "no_decision",
                    "provider_length", "provider_content_filter", "provider_error"]
    detail: str


# ---------------------------------------------------------------------------------------------
# Incident classes and inventory (§5.8)
# ---------------------------------------------------------------------------------------------
class DetectorResult(BaseModel):
    matched: bool
    findings: list[str] = []


class IncidentClassSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    family: str
    target_kinds: set[str]
    required_signals: set[str]
    runbook_ids: list[str]
    branch_runbook_ids: list[str] = []
    strategy: str
    tool_tags: set[str]
    max_steps: int = 8
    detector: Any                             # Callable[[MetricSnapshot], DetectorResult], pure


class AlertNotification(BaseModel):
    """Vendor-neutral translation of one Alertmanager alert (§5, ACR-0003): the same for push and pull."""
    fingerprint: str
    status: Literal["firing", "resolved"]
    starts_at: datetime
    ends_at: datetime | None = None
    updated_at: datetime | None = None        # ACR-0009: when Alertmanager last received it (a renewal, not presence)
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}


class HostInfo(BaseModel):
    name: str
    executors: dict[str, str]                 # executor → endpoint URL (no credentials)
    alertmanager: str | None = None           # ACR-0003: the host's Alertmanager URL (not an executor: no token)


class TargetInfo(BaseModel):
    ref: TargetRef
    scope: str = "lab"
    depends_on: list[TargetRef] = []
    http_endpoints: list[str] = []
    tcp_ports: list[int] = []
    mounts: list[str] = []
    networks: list[str] = []             # E2E-2: the networks a container is assigned to (inventory `networks`)
    database: str | None = None          # dbname read by the db-probe (inventory `database`)


# ---------------------------------------------------------------------------------------------
# Audit (§5.7)
# ---------------------------------------------------------------------------------------------
class AuditRecord(BaseModel):
    audit_id: str
    incident_id: str | None
    at: datetime
    category: Literal["tool", "decision", "incident", "access", "security"]
    event: str
    capability: str | None = None
    arguments: dict[str, JsonValue] | None = None
    policy_rule: str | None = None
    policy_version: str | None = None
    actor: str | None = None
    evidence_id: str | None = None
    detail: dict[str, JsonValue] = {}
