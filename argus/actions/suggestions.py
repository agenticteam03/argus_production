"""Action suggestions, basis computation, and candidate evaluation (ACR-0019 §3.3, §3.5).

Suggestions are read-only text hints for human operators and never execute directly.
Basis is computed by code from cited grounds (runbook, memory, reference, operator).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from argus.actions.catalog import is_action_permitted_on_service
from argus.actions.risk import RiskColor, RiskTable, resolve_proposal_risk

if TYPE_CHECKING:
    from argus.actions.cards import ActionCard, ServiceCard
    from argus.domain.model import TargetRef


class Basis(StrEnum):
    runbook = "runbook"
    memory = "memory"
    reference = "reference"
    operator = "operator"
    none = "none"


@dataclass(frozen=True)
class ActionSuggestion:
    target: TargetRef
    text: str
    action: str | None = None
    closest_capability: str | None = None
    basis: Basis = Basis.none
    grounds: list[str] = field(default_factory=list)
    risk_color: RiskColor = RiskColor.green
    is_executable: bool = False  # Suggestions in Phase 17 are strictly non-executable text for operators


def compute_basis(grounds: list[str]) -> Basis:
    """Computes the basis strictly by code from cited grounds.

    - RB-* -> runbook
    - mem-* -> memory of verified actions
    - ref-* -> curated reference documentation
    - op-* -> operator manual guidance
    Any uncited or unverified ground results in Basis.none (downgraded to suggestion).
    """
    for g in grounds:
        if g.startswith("RB-"):
            return Basis.runbook
        if g.startswith("mem-"):
            return Basis.memory
        if g.startswith("ref-"):
            return Basis.reference
        if g.startswith("op-"):
            return Basis.operator
    return Basis.none


def suggest_action(
    target: TargetRef,
    text: str,
    closest_capability: str | None = None,
    grounds: list[str] | None = None,
    risk_color: RiskColor = RiskColor.green,
) -> ActionSuggestion:
    """Creates a human-readable action suggestion for the operator."""
    cited_grounds = grounds or []
    basis = compute_basis(cited_grounds)
    return ActionSuggestion(
        target=target,
        text=text,
        action=closest_capability,
        closest_capability=closest_capability,
        basis=basis,
        grounds=cited_grounds,
        risk_color=risk_color,
        is_executable=False,
    )


def evaluate_candidate_actions(
    target: TargetRef,
    service_card: ServiceCard,
    action_cards: dict[str, ActionCard],
    risk_table: RiskTable,
    observations: dict[str, Any],
    grounds: list[str] | None = None,
    is_victim: bool = False,
) -> list[ActionSuggestion]:
    """Evaluates candidate actions for a target against service card, action cards, and observations.

    Enforces:
    - Never restarting the victim container of an external dependency failure (RB-002, RB-003).
    - ServiceCard safe_actions and never lists.
    - RiskTable forbidden checks.
    - ActionCard preconditions evaluated by AST without eval.
    """
    candidates: list[ActionSuggestion] = []
    cited_grounds = grounds or []
    basis = compute_basis(cited_grounds)

    for action_name, card in action_cards.items():
        # Rule: restarting the victim instead of the cause is strictly forbidden
        if is_victim and action_name == "container.restart":
            continue

        # Service Card authorization
        if not is_action_permitted_on_service(action_name, service_card):
            continue

        # Base risk lookup
        base_color = risk_table.lookup(action_name, service_card.kind)
        if base_color == RiskColor.forbidden:
            continue

        # Action Card preconditions
        if not card.check_preconditions(observations):
            continue

        # Color elevation
        resolved_color = resolve_proposal_risk(
            risk_table=risk_table,
            action=action_name,
            target_kind=service_card.kind,
            criticality=service_card.criticality,
            judge_verdict="agree",
        )

        candidates.append(
            ActionSuggestion(
                target=target,
                action=action_name,
                closest_capability=card.model_name,
                text=f"Candidate remediation: execute {action_name} on {target}",
                basis=basis,
                grounds=cited_grounds,
                risk_color=resolved_color,
                is_executable=False,
            )
        )

    return candidates
