"""ACR-0021 (T-0045 B4): the verdict fields of `GET /api/v1/incidents/{id}`, for the UI's verdict card.

A pure function of the stored incident, its class, its evidence and the declared dependencies: no model call, no host
read, no new store query beyond what the route already reads. Unknown stays unknown: a missing signal or a failed
read is listed under `not_checked`, never counted as healthy.
"""
from __future__ import annotations

import re
from collections import deque

from argus.domain.model import EvidenceRecord, Incident, IncidentClassSpec, IncidentOutcome

CONFIDENCE = {"high": (0.9, "High"), "medium": (0.6, "Medium"), "low": (0.3, "Low")}
HIGHLIGHTS = 3
MISSING = "signal missing (unknown, not healthy): "           # the detectors' own wording (classes.py)

# class -> (what the UI calls the problem, the kind in `cause`)
CLASS_TEXT = {
    "container_restart_loop": ("Restart loop", "restart_loop"),
    "dependency_unavailable": ("Dependency unavailable", "dependency"),
    "health_check_failed": ("Health check failing", "health_check"),
    "postgresql_connection_exhaustion": ("Connection slots exhausted", "connection_exhaustion"),
    "nginx_upstream_failure": ("Gateway errors", "gateway_error"),
    "cpu_saturation": ("CPU saturation", "cpu_saturation"),
    "disk_pressure": ("Disk pressure", "disk_pressure"),
    "monitoring_blind_spot": ("Monitoring blind spot", "blind_spot"),
}
# outcome -> a sentence for what is not a diagnosis; `{name}` is the target's short name
OUTCOME_TEXT = {
    IncidentOutcome.no_incident: "No incident: {name} looks healthy.",
    IncidentOutcome.undiagnosable: "Argus could not diagnose {name}: the evidence it needed was not available.",
    IncidentOutcome.unsupported_escalated: "{name} is not covered by a known incident class; Argus escalated it to a person.",
    IncidentOutcome.no_action_escalated: "Argus escalated {name} to a person.",
    IncidentOutcome.refused: "Argus refused the request for {name}.",
    IncidentOutcome.resolved_externally: "Every alert for {name} resolved before a run started.",
}


def first_sentence(text: str | None) -> str | None:
    text = (text or "").strip()
    return re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0] if text else None


def _first_line(text: str | None) -> str:
    return (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""


def _findings(inc: Incident, spec: IncidentClassSpec | None) -> list[str]:
    """The incident's findings without the runner's `<class>: ` prefix and its `also matched:` notes."""
    prefix = f"{spec.name}: " if spec else ""
    return [f[len(prefix):] if prefix and f.startswith(prefix) else f for f in inc.findings
            if not f.startswith("also matched:")]


def _severity(inc: Incident, spec: IncidentClassSpec | None) -> str | None:
    if inc.outcome == IncidentOutcome.no_incident:
        return "ok"
    if inc.outcome in (IncidentOutcome.undiagnosable, IncidentOutcome.unsupported_escalated):
        return "warning"
    return spec.severity if spec else None


def _summary(inc: Incident, spec: IncidentClassSpec | None) -> str:
    name = inc.target.name
    if inc.outcome == IncidentOutcome.diagnosed:
        finding = next((f for f in _findings(inc, spec) if not f.startswith(MISSING)), None)
        label = CLASS_TEXT.get(spec.name if spec else "", (None, None))[0]
        if finding and label:
            return f"{label} on {name}: {finding}"
        if first_sentence(inc.diagnosis):
            return first_sentence(inc.diagnosis)
    if inc.outcome in OUTCOME_TEXT:
        return OUTCOME_TEXT[inc.outcome].format(name=name)
    return first_sentence(inc.diagnosis) or f"The investigation of {name} has not finished."


def cause_path(depends: dict[str, list[str]], target: str, root: str | None) -> list[str]:
    """The shortest path over declared dependencies from the target to its root cause; `[target]` when they are the
    same; `[]` without a root cause or without a path."""
    if not root:
        return []
    if root == target:
        return [target]
    came, queue = {target: None}, deque([target])
    while queue and root not in came:
        here = queue.popleft()
        for nxt in depends.get(here, []):
            if nxt not in came:
                came[nxt] = here
                queue.append(nxt)
    if root not in came:
        return []
    path, step = [], root
    while step is not None:
        path.append(step)
        step = came[step]
    return path[::-1]


def hypotheses_view(rows: list[dict], evidence: list[EvidenceRecord], show_evidence: bool) -> tuple[list[dict], bool]:
    """ACR-0024 §3.6 (T-0047 H3): the final decision's hypotheses, by rank, and whether the chosen one is not ranked
    first. `for` / `against` count the cited records that are stored evidence of the incident; the ids themselves only
    with `show_evidence` (a viewer gets the counts, as for `evidence_highlights`)."""
    if not rows:
        return [], False
    last = max(r["step"] for r in rows)
    stored = {e.evidence_id for e in evidence}
    out = []
    for r in sorted((r for r in rows if r["step"] == last), key=lambda r: r["rank"]):
        h = {"id": r["hypothesis_id"], "statement": r["statement"], "cause_class": r["cause_class"],
             "target": r["target"], "relation": r["relation"], "status": r["status"], "rank": r["rank"],
             "chosen": r["chosen"], "support": {"score": r["score"],
                                                "for": len({i for i in r["support_ids"] if i in stored}),
                                                "against": len({i for i in r["against_ids"] if i in stored})}}
        if show_evidence:
            h["support_ids"], h["against_ids"] = list(r["support_ids"]), list(r["against_ids"])
        out.append(h)
    return out, any(h["chosen"] and h["rank"] != 1 for h in out)


def build_verdict(inc: Incident, spec: IncidentClassSpec | None, evidence: list[EvidenceRecord], cited: list[str],
                  depends: dict[str, list[str]], show_evidence: bool, hypotheses: list[dict] | None = None) -> dict:
    """`cited`: the evidence ids the conclusion cites (the `incident.recorded` audit event). `show_evidence`: False for a
    viewer, whose view carries no evidence text (so no highlights). `hypotheses`: the incident's stored rows
    (`incident_hypothesis`, every step)."""
    by_id = {e.evidence_id: e for e in evidence}
    highlights = []
    if show_evidence:
        for eid in dict.fromkeys(cited):
            if eid in by_id and len(highlights) < HIGHLIGHTS:
                highlights.append({"evidence_id": eid, "text": _first_line(by_id[eid].model_text), "stance": "supports"})
    not_checked = [f"{e.capability} on {e.target} · {e.status}" for e in evidence if e.status != "ok"]
    for f in _findings(inc, spec):
        if f.startswith(MISSING):
            not_checked.append(f"{f[len(MISSING):].strip()} · no fresh sample")
        elif f.startswith("metrics stale or unavailable"):
            not_checked.append("metrics · stale or unavailable")           # the cause text is not repeated here
    cause = None
    if inc.root_cause_target:
        score, label = CONFIDENCE.get(inc.confidence or "", (None, None))
        cause = {"target": inc.root_cause_target, "kind": CLASS_TEXT.get(spec.name if spec else "", (None, None))[1],
                 "statement": first_sentence(inc.diagnosis), "confidence": score, "confidence_label": label}
    ranked, disagrees = hypotheses_view(hypotheses or [], evidence, show_evidence)
    return {"severity": _severity(inc, spec), "summary": _summary(inc, spec), "cause": cause,
            "evidence_highlights": highlights, "not_checked": list(dict.fromkeys(not_checked)),
            "cause_path": cause_path(depends, str(inc.target), inc.root_cause_target),
            "duration_ms": (round((inc.closed_at - inc.opened_at).total_seconds() * 1000) if inc.closed_at else None),
            "next_actions": [],                            # until the runbook Actions section exists
            "hypotheses": ranked, "ranking_disagrees": disagrees}
