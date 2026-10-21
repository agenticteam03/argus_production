"""ACR-0024 §3.3 (T-0047 H2): the support score and the ranking of a decision's hypotheses, computed in Python, never
by the model.

`score = Σ weight(each counted supporting record) − Σ weight(each counted record against) − untested_penalty`

A cited record counts by what it is evidence of, relative to the hypothesis: an observation or a metric snapshot of
the hypothesis's **own** target counts once per distinct record, at most `max_target_records` of them; the generic
kinds (an observation or snapshot of **another** target, an alert, a reported symptom) count **once per kind** per
side, however many are cited, so a hypothesis cannot climb by citing every alert. An id that is not stored evidence
of the incident counts for nothing (the harness reports it, §11.3). Ties: more distinct supporting records that no
other hypothesis cites, then the order given. The ranking never changes the conclusion: `ranking_disagrees` only
says that the chosen hypothesis is not ranked first.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

OWN = ("observation", "metric_snapshot")          # what can show a target's own state
KEYS = {"weights", "untested_penalty", "max_target_records"}
WEIGHT_KEYS = {"own_observation", "own_metric_snapshot", "other_observation", "alert", "peer_finding",
               "reported_symptom"}


@dataclass(frozen=True)
class Weights:
    own_observation: float = 3.0
    own_metric_snapshot: float = 2.0
    other_observation: float = 1.0
    alert: float = 1.0
    peer_finding: float = 1.0                     # no peer finding is cited by an evidence id yet (§23)
    reported_symptom: float = 0.5
    untested_penalty: float = 0.5
    max_target_records: int = 3

    @classmethod
    def from_data(cls, data: dict | None) -> "Weights":
        """`config/ranking.yaml`. Fail closed: an unknown key, a missing weight or a negative number refuses the file."""
        if not isinstance(data, dict) or set(data) - KEYS:
            raise ValueError(f"ranking: unknown keys {sorted(set(data) - KEYS) if isinstance(data, dict) else data}")
        weights = data.get("weights")
        if not isinstance(weights, dict) or set(weights) != WEIGHT_KEYS:
            raise ValueError(f"ranking.weights must name exactly {sorted(WEIGHT_KEYS)}")
        values = {**weights, "untested_penalty": data.get("untested_penalty"),
                  "max_target_records": data.get("max_target_records")}
        for k, v in values.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise ValueError(f"ranking: {k} must be a number ≥ 0, not {v!r}")
        if not isinstance(values["max_target_records"], int) or values["max_target_records"] < 1:
            raise ValueError("ranking: max_target_records must be an integer ≥ 1")
        return cls(**{k: (v if k == "max_target_records" else float(v)) for k, v in values.items()})


def load_ranking(config_dir: Path) -> Weights:
    """`config/ranking.yaml`, validated (ValueError); no file = the ACR-0024 initial weights."""
    path = config_dir / "ranking.yaml"
    if not path.exists():
        return Weights()
    return Weights.from_data(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Ranked:
    id: str
    score: float
    rank: int                                     # 1 = the evidence favours it most
    counted_for: int                              # records that scored for it ("supported by N")
    counted_against: int                          # records that scored against it ("contradicted by M")


def _side(ids: list[str], target: str | None, evidence: dict, w: Weights) -> tuple[float, int]:
    """The weight of one side (for or against) of one hypothesis, and how many records counted."""
    own: list[float] = []
    generic: dict[str, float] = {}
    for i in dict.fromkeys(ids):                  # a record cited twice is one record
        e = evidence.get(i)
        if e is None:
            continue
        kind, about = getattr(e, "kind", None), getattr(e, "target", None)
        if kind in OWN and target is not None and about == target:
            own.append(w.own_observation if kind == "observation" else w.own_metric_snapshot)
        elif kind in OWN:
            generic["other_observation"] = w.other_observation
        elif kind == "alert":
            generic["alert"] = w.alert
        elif kind == "reported_symptom":
            generic["reported_symptom"] = w.reported_symptom
    own = sorted(own, reverse=True)[:w.max_target_records]
    return sum(own) + sum(generic.values()), len(own) + len(generic)


def rank(hypotheses: list, evidence: list, weights: Weights | None = None) -> list[Ranked]:
    """The hypotheses ranked (same order as given), each with its score; `evidence` is the incident's EvidenceRefs."""
    w = weights or Weights()
    by_id = {e.evidence_id: e for e in evidence}
    cited_by: dict[str, set[str]] = {}
    for h in hypotheses:
        for i in set(h.support) | set(h.against):
            cited_by.setdefault(i, set()).add(h.id)
    rows = []
    for order, h in enumerate(hypotheses):
        plus, n_for = _side(h.support, h.target, by_id, w)
        minus, n_against = _side(h.against, h.target, by_id, w)
        score = round(plus - minus - (w.untested_penalty if h.status == "untested" else 0.0), 3)
        unique = sum(1 for i in set(h.support) if i in by_id and cited_by.get(i) == {h.id})
        rows.append((h.id, score, unique, order, n_for, n_against))
    ranks = {r[0]: n for n, r in enumerate(sorted(rows, key=lambda r: (-r[1], -r[2], r[3])), start=1)}
    return [Ranked(id=i, score=s, rank=ranks[i], counted_for=f, counted_against=a) for i, s, _, _, f, a in rows]


def ranking_disagrees(ranked: list[Ranked], chosen: str | None) -> bool:
    """§3.3: the chosen hypothesis is not ranked first (the UI says "the evidence favours <first>")."""
    if not chosen:
        return False
    return next((r.rank for r in ranked if r.id == chosen), None) not in (None, 1)
