"""An evaluation case and its label (ARCHITECTURE §21.2 "Dataset"). Unknown keys are refused."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Category = Literal["class", "unsupported", "stale_metrics", "forbidden_target", "healthy_check", "tool_failure",
                   "ambiguous"]


class ExpectedHypotheses(BaseModel):
    """ACR-0024 §3.8: what a good list holds; each entry is a target or a cause class."""
    model_config = ConfigDict(extra="forbid")
    supported: list[str] = []                     # the cause (default: the label's `root_cause`)
    ruled_out: list[str] = []                     # what a careful run considers and rules out


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    outcome: str | list[str]
    incident_class: str | None = Field(default=None, alias="class")
    root_cause: str | None = None
    abstain: bool = False                         # the right answer claims no diagnosis
    model_calls: int | None = None                # exact number expected (safety cases: 0)
    diagnosis_any: list[str] = []
    findings_any: list[str] = []
    runbooks: list[str] = []                      # supporting runbooks, for recall@3
    expected_hypotheses: ExpectedHypotheses | None = None    # ACR-0024 §3.8 (T-0047 H4)

    def expected_causes(self) -> list[str]:
        """The entries a top-ranked hypothesis should match: `expected_hypotheses.supported`, else `root_cause`."""
        if self.expected_hypotheses and self.expected_hypotheses.supported:
            return list(self.expected_hypotheses.supported)
        return [self.root_cause] if self.root_cause else []

    def names_class(self) -> bool:
        """True when the label names `class`, also as `class: null` (= no class may match)."""
        return "incident_class" in self.model_fields_set

    def outcomes(self) -> list[str]:
        return self.outcome if isinstance(self.outcome, list) else [self.outcome]


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    category: Category
    target: str
    request: Literal["report", "check"]
    reason: str
    metrics: dict[str, dict[str, float | None]] = {}
    stale: bool = False
    fixtures: dict[str, dict[str, Any]] = {}
    secrets: list[str] = []
    label: Label


def load_cases(folder: Path) -> list[Case]:
    cases: list[Case] = []
    for path in sorted(Path(folder).glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            cases.append(Case.model_validate(raw))
        except ValidationError as e:
            raise ValueError(f"{path.name}: {e}") from e
    ids = [c.id for c in cases]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"duplicate case ids: {dup}")
    return cases
