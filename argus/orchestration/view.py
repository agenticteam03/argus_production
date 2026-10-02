"""The read-only view a diagnostic strategy decides from (v1.8 §10.3). Domain imports only."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from argus.domain.model import EvidenceRef, Incident, IncidentClassSpec, Passage, TargetRef


@dataclass
class InvestigationView:
    incident: Incident
    incident_class: IncidentClassSpec | None
    findings: list[str]
    passages: list[Passage]
    evidence: list[EvidenceRef]
    decisions_so_far: list[Any]
    offered_specs: list[Any]                    # CapabilitySpec, already filtered by policy/class/level
    scope: list[TargetRef]
    steps_left: int
    max_reads_per_step: int
    context_text: str = ""
    notes: list[str] = field(default_factory=list)
    down_executors: dict[str, str] = field(default_factory=dict)   # "executor@host" -> error category

    @property
    def evidence_ids(self) -> set[str]:
        return {e.evidence_id for e in self.evidence}
