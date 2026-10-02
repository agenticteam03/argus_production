"""Diagnostic strategies (v1.8 §10.3). A strategy only RETURNS decisions; it never executes anything.

Imports domain only; the model-tool harness is injected.
"""
from __future__ import annotations

from typing import Any, Protocol

from argus.domain.model import Escalate, InvalidDecision, ReadCall, TargetRef, UseReadTools
from argus.orchestration.view import InvestigationView


class DiagnosticStrategy(Protocol):
    name: str
    def next_step(self, view: InvestigationView) -> Any: ...


def evidence_pack_plan(target: TargetRef) -> list[ReadCall]:
    """The fixed, model-free Level 1 evidence pack (v1.8 §10.7)."""
    host_t = f"{target.host}/host:{target.host}"
    calls: list[ReadCall] = []
    if target.kind == "container":
        t = str(target)
        calls += [ReadCall(name="container.status", arguments={"target": t}),
                  ReadCall(name="container.resources", arguments={"target": t}),
                  ReadCall(name="container.health", arguments={"target": t}),
                  ReadCall(name="container.logs", arguments={"target": t, "tail": 30})]
    calls += [ReadCall(name="host.memory", arguments={"target": host_t}),
              ReadCall(name="host.cpu", arguments={"target": host_t})]
    return calls


class EvidencePackStrategy:
    name = "evidence_pack"
    last_source = "rule"

    def next_step(self, view: InvestigationView):
        if not any(isinstance(d, UseReadTools) for d in view.decisions_so_far):
            return UseReadTools(calls=evidence_pack_plan(view.incident.target))
        return Escalate(reason="evidence pack collected; no diagnosis is claimed",
                        evidence_ids=sorted(view.evidence_ids))


class ModelLoopStrategy:
    name = "model_loop"

    def __init__(self, harness: Any | None):
        self.harness = harness
        self.last_source = "rule"          # "model" when the harness produced the decision

    def next_step(self, view: InvestigationView):
        if self.harness is None:
            self.last_source = "rule"
            return Escalate(reason="no model configured; escalating with deterministic evidence",
                            evidence_ids=sorted(view.evidence_ids))
        self.last_source = "model"
        return self.harness.decide(view)


class PlanThenReasonStrategy:
    """A fixed first round from the evidence pack, then the model loop."""
    name = "plan_then_reason"

    def __init__(self, harness: Any | None):
        self.loop = ModelLoopStrategy(harness)
        self.last_source = "rule"

    def next_step(self, view: InvestigationView):
        if not any(isinstance(d, UseReadTools) for d in view.decisions_so_far):
            self.last_source = "rule"
            return UseReadTools(calls=evidence_pack_plan(view.incident.target)[:3])
        d = self.loop.next_step(view)
        self.last_source = self.loop.last_source
        return d


def is_invalid(decision: Any) -> bool:
    return isinstance(decision, InvalidDecision)
