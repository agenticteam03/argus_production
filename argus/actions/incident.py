"""Read-only action candidates derived from reviewed cards and stored incident evidence."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from argus.actions.cards import ActionCard, load_action_cards
from argus.actions.catalog import get_action_spec
from argus.actions.preconditions import evaluate_precondition
from argus.actions.risk import RiskTable
from argus.actions.suggestions import evaluate_candidate_actions
from argus.domain.model import EvidenceRecord, Incident, IncidentOutcome, TargetRef

_METADATA = re.compile(r"```yaml\s*\n(.*?)\n```", re.S)
_MAX_OBSERVATION_AGE = timedelta(seconds=90)
_FUTURE_TOLERANCE = timedelta(seconds=5)
_ACTION_DENIED_HOSTS = frozenset({"vm-095"})


def _protected_target(name: str) -> bool:
    return (name.startswith("argus-v18-") or name in {"prometheus", "alertmanager"}
            or "gateway" in name or "probe" in name)


def _fresh_observation(evidence: EvidenceRecord, now: datetime) -> bool:
    source = evidence.source_time
    collected = evidence.collected_at
    if source is None or source.tzinfo is None or collected.tzinfo is None:
        return False
    return (source <= now + _FUTURE_TOLERANCE and collected <= now + _FUTURE_TOLERANCE
            and source <= collected + _FUTURE_TOLERANCE
            and now - source <= _MAX_OBSERVATION_AGE)


@dataclass(frozen=True)
class RunbookAction:
    runbook_id: str
    action: str
    target_role: str
    service_role: str
    when: str


def load_runbook_actions(directory: Path | str, cards: dict[str, ActionCard]) -> dict[str, list[RunbookAction]]:
    """Load only reviewed runbook actions that agree with an action card."""
    actions: dict[str, list[RunbookAction]] = {}
    for path in sorted(Path(directory).glob("RB-*.md")):
        match = _METADATA.search(path.read_text(encoding="utf-8"))
        if not match:
            continue
        metadata = yaml.safe_load(match.group(1)) or {}
        runbook_id = metadata.get("id")
        if not isinstance(runbook_id, str):
            continue
        for entry in metadata.get("actions") or []:
            if not isinstance(entry, dict):
                raise ValueError(f"{path.name}: an action must be a mapping")
            name = entry.get("action")
            if not isinstance(name, str):
                raise ValueError(f"{path.name}: action name is required")
            get_action_spec(name)
            card = cards.get(name)
            if card is None or runbook_id not in card.sources:
                raise ValueError(f"{path.name}: {name} has no matching action-card source")
            when = entry.get("when")
            if not isinstance(when, str) or when not in card.preconditions:
                raise ValueError(f"{path.name}: {name} guard must match its action card")
            action = RunbookAction(runbook_id, name, str(entry.get("target_role", "")),
                                   str(entry.get("service_role", "")), when)
            if action.target_role != "root_cause" or not action.service_role:
                raise ValueError(f"{path.name}: {name} needs a root-cause target and service role")
            actions.setdefault(runbook_id, []).append(action)
    return actions


class ActionPolicy:
    """Evaluates candidates only from known actions, cited runbooks and recent observations."""

    def __init__(self, cards: dict[str, ActionCard], risk_table: RiskTable,
                 runbook_actions: dict[str, list[RunbookAction]]) -> None:
        self.cards = cards
        self.risk_table = risk_table
        self.runbook_actions = runbook_actions

    @classmethod
    def from_paths(cls, config_dir: Path, runbooks_dir: Path) -> ActionPolicy:
        cards = load_action_cards(config_dir / "actions")
        risk_path = config_dir / "risk.yaml"
        risk = RiskTable.from_yaml(risk_path) if risk_path.is_file() else RiskTable({})
        return cls(cards, risk, load_runbook_actions(runbooks_dir, cards) if cards else {})

    def next_actions(self, inc: Incident, evidence: list[EvidenceRecord], recalled_runbooks: set[str],
                     inventory, now: datetime | None = None) -> list[dict]:
        if inc.outcome != IncidentOutcome.diagnosed or not inc.root_cause_target:
            return []
        try:
            target = TargetRef.parse(inc.root_cause_target)
        except ValueError:
            return []
        if target.host in _ACTION_DENIED_HOSTS or _protected_target(target.name):
            return []
        info = inventory.target(target)
        if info is None or info.scope != "lab" or not target.name.startswith("argus-lab-"):
            return []
        service = info.service_card()
        if service is None or target.kind != "container":
            return []
        at = now or datetime.now(timezone.utc)
        current = [e for e in evidence if e.capability == "container.status" and e.target == str(target)
                   and e.status == "ok" and e.kind == "observation"
                   and _fresh_observation(e, at)]
        if not current:
            return []
        observed = max(current, key=lambda e: e.source_time)
        values = observed.values.get("values")
        if not isinstance(values, dict):
            return []
        # X-5: besides the cause's own status, the newest record of each kind that ties the incident's target to it (the
        # reported symptom, the detector's metric snapshot, the recorded links), so a reviewer sees the failing dependent
        supporting = []
        for kind, capability in (("reported_symptom", None), ("metric_snapshot", None),
                                 ("observation", "network.link_states")):
            found = [e for e in evidence if e.target == str(inc.target) and e.kind == kind
                     and (capability is None or (e.capability == capability and e.status == "ok"))]
            if found:
                supporting.append(max(found, key=lambda e: e.collected_at).evidence_id)
        # the cause's declared dependencies: a cause found by elimination ("its dependency is running, no link broken")
        # is only as good as the read that shows it, and the judge sees only what the candidate cites
        for dependency in info.depends_on:
            found = [e for e in evidence if e.capability == "container.status" and e.target == str(dependency)
                     and e.status == "ok" and e.kind == "observation"]
            if found:
                supporting.append(max(found, key=lambda e: e.collected_at).evidence_id)
        offered: dict[str, tuple[ActionCard, str]] = {}
        for runbook_id in recalled_runbooks:
            for action in self.runbook_actions.get(runbook_id, []):
                if action.service_role != service.role or not evaluate_precondition(action.when, values):
                    continue
                card = self.cards[action.action]
                offered[action.action] = (card, runbook_id)
        result = []
        for name, (card, ground) in offered.items():
            observations = values
            if name == "network.restore":
                # the card's preconditions name its arguments: derive them as the proposer does, only when unambiguous
                declared, attached = list(info.networks or []), values.get("networks")
                if len(declared) != 1 or not isinstance(attached, list) or len(attached) != 1:
                    continue
                observations = {**values, "declared_networks": declared, "connect_network": declared[0],
                                "disconnect_network": attached[0]}
            suggestions = evaluate_candidate_actions(
                target, service, {name: card}, self.risk_table, observations, grounds=[ground], is_victim=False,
                verified_sources={ground})
            for suggestion in suggestions:
                result.append({"action": suggestion.action, "target": str(target), "text": suggestion.text,
                               "basis": suggestion.basis.value, "grounds": suggestion.grounds,
                               "evidence_refs": [observed.evidence_id, *supporting],
                               "risk_color": suggestion.risk_color.value,
                               "is_executable": False})
        return result
