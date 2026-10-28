"""Phase 20 (X-4): the fresh precheck and the verification sample the executor needs, read from the target.

Both are built from injected reads (an audited `container.status`, a signal sampler, the detector, the host lease),
so the dispatch module keeps no model, harness or executor dependency. Nothing in production constructs them while
`write_gate.open` is empty.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from argus.actions.execution import Precheck, Verification
from argus.actions.preconditions import evaluate_precondition
from argus.actions.remediation import FrozenProposal, RemediationRefused, verify_frozen_proposal
from argus.domain.model import IncidentStatus, Observation, TargetRef

OPEN_STATES = (IncidentStatus.queued, IncidentStatus.running)


def status_from_observation(obs: Observation) -> tuple[dict[str, Any], datetime]:
    """An ok `container.status` observation's values and the time the source measured them."""
    if obs.capability != "container.status" or obs.status != "ok":
        raise RemediationRefused("a current container status is unavailable")
    return dict(obs.values), obs.source_time or obs.collected_at


class LivePrecheck:
    """`snapshot(proposal, at) -> Precheck`: every field read now, never copied from the proposal."""

    def __init__(self, *, rows, inventory, policy_version: str, cards: dict,
                 read_status: Callable[[str], tuple[dict[str, Any], datetime]],
                 detector_firing: Callable[[Any], bool], host_lease_clear: Callable[[str], bool]):
        self.rows, self.inventory, self.policy_version, self.cards = rows, inventory, policy_version, cards
        self.read_status, self.detector_firing, self.host_lease_clear = read_status, detector_firing, host_lease_clear

    def __call__(self, proposal: FrozenProposal, at: datetime) -> Precheck:
        verify_frozen_proposal(proposal)
        data = proposal.input
        card = self.cards.get(data.capability)
        if card is None:
            raise RemediationRefused("no reviewed action card for this capability")
        values, observed_at = self.read_status(data.target)
        precondition_values = {**data.arguments, **values}
        identity = {name: values.get(name) for name in card.identity_fields}
        if not identity or not all(isinstance(v, str) and v for v in identity.values()):
            raise RemediationRefused("the target's identity is unavailable")
        incident = self.rows.get_incident(data.incident_id)
        return Precheck(
            target_identity=identity,
            inventory_version=self.inventory.version(),
            policy_version=self.policy_version,
            evidence_version=str(self.rows.evidence_state(data.incident_id)[0]),
            observed_at=observed_at,
            incident_open=incident is not None and incident.status in OPEN_STATES,
            class_detected=incident is not None and bool(self.detector_firing(incident)),
            action_preconditions_met=all(evaluate_precondition(expr, precondition_values)
                                         for expr in card.preconditions),
            host_lease_clear=bool(self.host_lease_clear(TargetRef.parse(data.target).host)))


class LiveVerification:
    """`sample(action_id, at) -> Verification | None`: the frozen prediction's signal on its target, and whether the
    incident's detector has cleared. None while no sample exists; the executor keeps waiting until its deadline."""

    def __init__(self, *, rows, read_signal: Callable[[str, str], tuple[str, datetime] | None],
                 detector_firing: Callable[[Any], bool]):
        self.rows, self.read_signal, self.detector_firing = rows, read_signal, detector_firing

    def __call__(self, action_id: str, at: datetime) -> Verification | None:
        action = self.rows.get_action(action_id)
        if action is None:
            raise RemediationRefused("action ID is missing")
        proposal = self.rows.get_action_proposal(action["proposal_id"])
        verify_frozen_proposal(proposal)
        prediction = proposal.input.prediction
        sampled = self.read_signal(prediction.signal, prediction.target)
        if sampled is None:
            return None
        actual, sampled_at = sampled
        incident = self.rows.get_incident(proposal.input.incident_id)
        return Verification(sampled_at=sampled_at, detector_cleared=incident is not None
                            and not self.detector_firing(incident),
                            signal=prediction.signal, target=prediction.target, actual=str(actual))
