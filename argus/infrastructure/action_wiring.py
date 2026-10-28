"""Phase 20 (X-9): build the supervised-action path for the worker. Closed by default.

Every piece here composes something already reviewed: the HTTP gateway client (phase 19), the judge adapter (phase 18),
`LivePrecheck` and `LiveVerification` (X-4), and `InvokeCapability` for the audited `container.status` read. This module
adds only the glue and one decision, written down here:

*The proposer is deterministic.* ACR-0019 lets the model draft a proposal; this first version does not call a model for
it. It builds the proposal from the reviewed candidate, the action card and a fresh read of the target, and the judge
(a second model) still reviews the frozen result. That is narrower than the ACR allows, so it adds no authority. It
proposes only for an action without parameters and only for an incident class with a reviewed verification signal
(`VERIFY_SIGNALS`); anything else is no proposal and the incident escalates, as it does today.

The path is built only when `ARGUS_ACTION_PATH=1` **and** `write_gate.open` names a pair. With the flag set and the
gate open, anything missing (gateway URL, token file, judge key, runner) stops the start instead of being ignored.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from argus.actions.live import LivePrecheck, LiveVerification, identity_of, status_from_observation
from argus.actions.remediation import Alternative, Prediction, ProposalInput, RemediationRefused
from argus.application.correlation import detected_class
from argus.application.invoke_capability import InvocationContext
from argus.domain.model import TargetRef

log = logging.getLogger(__name__)

# incident class -> (signal on the incident's own target, least value that counts as healthy). A class absent here gets
# no proposal: the verification must be a reviewed fact, not a guess.
VERIFY_SIGNALS: dict[str, tuple[str, float]] = {
    "dependency_unavailable": ("dependency_probe_min", 1.0),
    # S4: the restarted worker must process again; any positive five-minute rate counts (the detector wants exactly 0)
    "worker_stalled": ("jobs_processed_rate", 0.01),
}
HEALTHY_AT_LEAST = {signal: minimum for signal, minimum in VERIFY_SIGNALS.values()}
# actions this proposer may propose: those whose reviewed card needs no argument (a card's optional parameters, such as
# `timeout`, are simply left out). An action with required choices, like network.restore's two networks, is not here.
ARGUMENTLESS_ACTIONS = frozenset({"container.start", "container.restart"})
PREDICTION_WINDOW_S = 120                      # ACR-0019 section 3.6's example; the same window as ACR-0035
EXTRACT_MAX = 480                              # the judge accepts at most 500 characters per extract


def gate_pairs(entries) -> frozenset[tuple[str, str]]:
    """`write_gate.open` as (capability, target) pairs. A malformed entry stops the start."""
    pairs: set[tuple[str, str]] = set()
    for item in entries or []:
        if (not isinstance(item, dict) or set(item) != {"capability", "target"}
                or not all(isinstance(value, str) and value for value in item.values())):
            raise SystemExit("write_gate.open entries must be exactly {capability, target}")
        pairs.add((item["capability"], item["target"]))
    return frozenset(pairs)


APPROVAL_ROW_METHODS = ("list_pending_approvals", "get_action_approval", "answer_action_approval")


def approval_rows(policy, store):
    """The rows behind the API's private login, approval and hold routes, or None. `build_api` mounts those routes only
    when this is not None, so they exist only while `write_gate.open` names a pair: there is nothing to approve before.
    It does not depend on ARGUS_ACTION_PATH (the API process has no action token). The routes keep their own guards: the
    private path, the approver role, two WebAuthn keys and a step-up."""
    if not gate_pairs(policy.write_gate_open):
        return None
    if not all(hasattr(store, method) for method in APPROVAL_ROW_METHODS):
        raise SystemExit("write_gate.open names a pair but the store has no approval tables")
    return store


class StatusReader:
    """`container.status` through the audited read path, for an incident: policy, redaction and audit all apply."""

    def __init__(self, invoke):
        self.invoke = invoke

    def __call__(self, incident, target: str) -> tuple[dict[str, Any], datetime]:
        ref = TargetRef.parse(target)
        ctx = InvocationContext(incident=incident, caller="action_path", scope={ref}, counters={})
        observation, _ = self.invoke(ctx, "container.status", {"target": target})
        return status_from_observation(observation)


class CandidateProposer:
    """`(incident, candidates, state) -> ProposalInput | None`, with no model call (see the module docstring)."""

    def __init__(self, *, rows, inventory, cards: dict, gate_open: frozenset, read_status: Callable,
                 policy_version: str):
        self.rows, self.inventory, self.cards, self.gate_open = rows, inventory, cards, gate_open
        self.read_status, self.policy_version = read_status, policy_version

    def __call__(self, incident, candidates: list[dict], state: dict) -> ProposalInput | None:
        rule = VERIFY_SIGNALS.get(incident.incident_class or "")
        if rule is None:
            log.info("no reviewed verification signal for class %s: no proposal", incident.incident_class)
            return None
        for candidate in candidates:
            card = self.cards.get(candidate["action"])
            if (card is None or candidate["action"] not in ARGUMENTLESS_ACTIONS
                    or (candidate["action"], candidate["target"]) not in self.gate_open):
                continue                                    # not released, or it needs arguments this proposer cannot set
            try:
                values, _ = self.read_status(incident, candidate["target"])
                identity = identity_of(card, values)
            except RemediationRefused as exc:
                log.info("no proposal for %s on %s: %s", candidate["action"], candidate["target"], exc)
                continue
            name = TargetRef.parse(candidate["target"]).name
            return ProposalInput(
                incident_id=incident.id, capability=candidate["action"], target=candidate["target"],
                target_identity=identity, arguments={}, root_cause=incident.root_cause_target or candidate["target"],
                rationale=self._rationale(incident, name, values, candidate["action"])
                + self._ruled_out(values, candidate["evidence_refs"], candidate["target"]),
                evidence_refs=list(candidate["evidence_refs"]),
                grounds=["runbook:" + ground for ground in candidate["grounds"]],
                prediction=Prediction(signal=rule[0], target=str(incident.target), expected="healthy",
                                      within_seconds=PREDICTION_WINDOW_S),
                alternatives=[Alternative(action="wait", why_not="The cause stays in place, so the dependent keeps failing.")],
                preview=f"{candidate['action']} on {name}", rollback=card.rollback,
                inventory_version=self.inventory.version(), policy_version=self.policy_version,
                evidence_version=str(self.rows.evidence_state(incident.id)[0]))
        return None


    def _ruled_out(self, values: dict, refs: list[str], cause: str) -> str:
        """What the cited reads already exclude, in plain words for the judge and the approver: no model text, and a
        fact only when the exclusion holds (an OOM kill or a restart count above zero is not 'ruled out'). A foreign
        `container.status` among the cited records is a declared dependency of the cause (incident.py cites no other)."""
        facts = []
        if values.get("oom_killed") is False:
            facts.append("no OOM kill")
        if values.get("restart_count") == 0:
            facts.append("0 restarts")
        by_id = {record.evidence_id: record for record in self.rows.get_evidence(list(refs))}
        for ref in refs:
            record = by_id.get(ref)
            seen = (record.values.get("values") or {}) if record is not None else {}
            if (record is not None and record.capability == "container.status" and record.status == "ok"
                    and record.target != cause and seen.get("state") == "running"):
                facts.append(f"dependency {TargetRef.parse(record.target).name} is running")
        return f" Ruled out by the cited reads: {'; '.join(facts)}." if facts else ""

    @staticmethod
    def _rationale(incident, name: str, values: dict, action: str) -> str:
        state = values.get("state", "not running")
        if incident.target.name == name:
            return f"{name} is {state} but its {incident.incident_class} persists; {action} on it addresses the cause."
        return (f"{name} is {state}; {action} on it addresses the cause of {incident.target.name}'s "
                f"{incident.incident_class}, not the symptom.")


class SignalSampler:
    """`(signal, target) -> (actual, sampled_at) | None` for `LiveVerification`. `actual` is "healthy" only when the fresh
    value reaches the reviewed minimum; a missing, stale or non-finite value is None (unknown, never healthy)."""

    def __init__(self, metrics, healthy_at_least: dict[str, float] | None = None):
        self.metrics, self.healthy_at_least = metrics, healthy_at_least or HEALTHY_AT_LEAST

    def __call__(self, signal: str, target: str):
        minimum = self.healthy_at_least.get(signal)
        if minimum is None:
            return None
        try:
            snapshot = self.metrics.snapshot(TargetRef.parse(target), {signal})
        except Exception as exc:  # noqa: BLE001 - any metrics failure is "no sample", never "healthy"
            log.info("no verification sample for %s on %s: %s", signal, target, type(exc).__name__)
            return None
        value = snapshot.values.get(signal)
        if snapshot.observed_at is None or value is None or not math.isfinite(value):
            return None
        return ("healthy" if value >= minimum else "unhealthy"), snapshot.observed_at


def class_detected(metrics, incident) -> bool:
    """Precheck: does the incident's class still match now? Any failure to know is False, so nothing is sent."""
    try:
        return detected_class(metrics, incident.target) == incident.incident_class
    except Exception:  # noqa: BLE001
        return False


def class_still_firing(metrics, incident) -> bool:
    """Verification: has the detector not cleared? Any failure to know is True, so a recovery is never claimed."""
    try:
        return detected_class(metrics, incident.target) == incident.incident_class
    except Exception:  # noqa: BLE001
        return True


class ReviewContext:
    """`proposal -> {evidence_extracts, ground_extracts, service_card, action_card}` for the judge: bounded excerpts of
    exactly the records the proposal cites, and the two reviewed cards."""

    def __init__(self, *, rows, inventory, cards: dict, runbooks_dir: Path):
        self.rows, self.inventory, self.cards, self.runbooks_dir = rows, inventory, cards, Path(runbooks_dir)

    def __call__(self, proposal) -> dict:
        data = proposal.input
        records = {record.evidence_id: record for record in self.rows.get_evidence(list(data.evidence_refs))}
        if set(records) != set(data.evidence_refs):
            raise RemediationRefused("a cited evidence record is missing")
        info = self.inventory.target(TargetRef.parse(data.target))
        service = info.service_card() if info is not None else None
        card = self.cards.get(data.capability)
        if service is None or card is None:
            raise RemediationRefused("reviewed service and action cards are required")
        return {"evidence_extracts": {key: _bounded(record.model_text) for key, record in records.items()},
                "ground_extracts": {ground: self._runbook(ground, data.capability) for ground in data.grounds},
                "service_card": service.model_dump() if hasattr(service, "model_dump") else asdict(service),
                "action_card": asdict(card) if is_dataclass(card) else dict(card)}

    def _runbook(self, ground: str, capability: str = "") -> str:
        runbook_id = ground.removeprefix("runbook:")
        paths = sorted(self.runbooks_dir.glob(f"{runbook_id}-*.md"))
        if not paths:
            raise RemediationRefused(f"runbook {runbook_id} is not in the library")
        text = paths[0].read_text(encoding="utf-8")
        text = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)
        declared = _declared_action(text, capability)
        if declared:          # X-5: the header alone (title, status) told the judge nothing about the action
            recovery = re.search(r"^## Recovery\s*\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M)
            title = text.strip().splitlines()[0].lstrip("# ").strip()
            text = f"{title}. Declared action: {declared}" + (f" Recovery: {recovery.group(1)}" if recovery else "")
        return _bounded(text)


def _declared_action(text: str, capability: str) -> str:
    """The runbook metadata's `actions:` entry for `capability`, as one sentence; "" when there is none."""
    match = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.S)
    try:
        metadata = yaml.safe_load(match.group(1)) if match else None
    except yaml.YAMLError:
        return ""
    entries = metadata.get("actions") or [] if isinstance(metadata, dict) else []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("action") == capability:
            return (f"{capability} on the {entry.get('target_role', '?')} service with role "
                    f"{entry.get('service_role', '?')} when {entry.get('when', '?')}. "
                    f"{entry.get('rationale', '')}").strip()
    return ""


def _bounded(text: str) -> str:
    collapsed = " ".join(str(text).split())
    if not collapsed:
        raise RemediationRefused("an extract is empty")
    return collapsed[:EXTRACT_MAX]


def build_action_path(s, *, store, policy, inventory, action_policy, metrics, invoke):
    """The worker's `OfflineActionPath`, or None while the path is off or the write gate is empty."""
    gate = gate_pairs(policy.write_gate_open)
    if not s.action_path:
        if gate:
            log.warning("write_gate.open names %d pair(s) but ARGUS_ACTION_PATH is off: nothing will act", len(gate))
        return None
    if not gate:
        log.info("ARGUS_ACTION_PATH is on but write_gate.open is empty: the action path is not built")
        return None
    problems = []
    if s.runner != "langgraph":
        problems.append("ARGUS_RUNNER must be langgraph")
    if not s.action_gateway_url:
        problems.append("ARGUS_ACTION_GATEWAY_URL is unset")
    if not Path(s.action_token_file).is_file():
        problems.append("the action token file is missing")
    judge_key = s.secret("openai_api_key")
    if not judge_key:
        problems.append("the judge's model key is missing")
    if not hasattr(store, "add_action_proposal"):
        problems.append("the store has no action tables")
    if problems:
        raise SystemExit("the action path is enabled and the write gate is open, but: " + "; ".join(problems))
    from argus.actions.gateway_client import HttpActionGateway
    from argus.adapters.outbound.judge import OpenAIJudge
    from argus.orchestration.action_path import OfflineActionPath
    cards = action_policy.cards
    reader = StatusReader(invoke)
    judge = OpenAIJudge(judge_key, s.judge_model, deciding_model=s.llm_model)
    # TASK-61: the approval notice (and a held-back proposal's escalation) goes out through the home host's
    # Alertmanager, on the security route (Telegram)
    home = inventory.host(s.home_host) if getattr(s, "home_host", "") else None
    notifier = escalation = None
    if home is not None and home.alertmanager:
        from argus.infrastructure.security_alerts import SecurityAlerts
        team = SecurityAlerts(store, home.alertmanager)
        notifier, escalation = team.notify_approval_waiting, team.notify_escalation
    else:
        log.warning("ARGUS_HOME_HOST names no host with an Alertmanager: approval and escalation notices will not "
                    "be sent")

    def snapshot(proposal, at):
        incident = store.get_incident(proposal.input.incident_id)
        return LivePrecheck(
            rows=store, inventory=inventory, policy_version=policy.version, cards=cards,
            read_status=lambda target: reader(incident, target),
            detector_firing=lambda found: class_detected(metrics, found),
            host_lease_clear=lambda host: True)(proposal, at)       # leases are process, not code (ACR-0019 section 3.11)

    verification = LiveVerification(rows=store, read_signal=SignalSampler(metrics),
                                    detector_firing=lambda found: class_still_firing(metrics, found))
    return OfflineActionPath(
        rows=store, action_policy=action_policy, inventory=inventory,
        proposer=CandidateProposer(rows=store, inventory=inventory, cards=cards, gate_open=gate, read_status=reader,
                                   policy_version=policy.version),
        judge_model=judge, judge_model_id=s.judge_model,
        judge_context=ReviewContext(rows=store, inventory=inventory, cards=cards, runbooks_dir=s.runbooks_dir),
        snapshot=snapshot, sample=verification,
        gateway=HttpActionGateway(s.action_gateway_url, s.action_token_file),
        gate_open=gate, daily_host_cap=s.action_daily_host_cap, approval_notifier=notifier,
        escalation_notifier=escalation)
