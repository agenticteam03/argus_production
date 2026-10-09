"""Replay one case through the real wiring with fixture executors and a fixed metric snapshot."""
from __future__ import annotations

import dataclasses
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.capabilities.spec import ExecutorError
from argus.domain.model import Incident, MetricSnapshot, RequestKind, TargetRef, TriggerKind, utcnow
from argus.evaluation.cases import Case
from argus.infrastructure.wiring import Settings, build
from argus.ports.ports import StaleMetrics
from argus.tooling.executors import ExecutorRegistry

EXECUTORS = ("docker_read", "host_probe", "network_probe", "db_probe", "prometheus")


@dataclass
class CaseRun:
    case_id: str
    outcome: str | None
    incident_class: str | None
    root_cause_target: str | None
    diagnosis: str | None
    findings: list[str]
    model_calls: int
    reads: list[tuple[str, str, str]]          # (capability, target, status) of every read stored as evidence
    passages: list[tuple[str, str]]            # (runbook_id, section) recalled
    audit_events: list[str]
    model_requests: list[str] = field(default_factory=list)   # the whole text of every model request
    duration_ms: int = 0
    trial: int = 1


class FixtureExecutor:
    """Answers a read from the case: `fixtures["path?k=v"]` (its parameters, sorted), else `fixtures[path]`, else
    `fixtures["*"]`; `{error: <category>}` fails the read, as the target service would."""

    def __init__(self, answers: dict[str, Any]):
        self.answers = answers

    def get(self, path: str, params: dict | None = None) -> Any:
        keyed = path + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
        if params and keyed in self.answers:            # a per-parameter answer (e.g. /dns?name=argus-lab-backend)
            answer = self.answers[keyed]
        elif path in self.answers:
            answer = self.answers[path]
        elif "*" in self.answers:
            answer = self.answers["*"]
        else:
            raise ExecutorError("not_found", f"no fixture for {path}")
        if isinstance(answer, dict) and set(answer) == {"error"}:
            raise ExecutorError(str(answer["error"]), f"fixture error for {path}")
        return answer

    def range(self, signal: str, target: TargetRef, minutes: int, step_s: int) -> list[tuple[float, float]]:
        """Metric history (the prometheus executor): `fixtures.prometheus.range.<signal>` as [seconds before now,
        value] pairs, cut to the window asked; none = no samples (the capability answers NO DATA, unknown)."""
        now = time.time()
        points = (self.answers.get("range") or {}).get(signal) or []
        return [(now + float(dt), float(v)) for dt, v in points if -float(dt) <= minutes * 60]


class CaseMetrics:
    def __init__(self, case: Case):
        self.case = case

    def snapshot(self, target: TargetRef, signals) -> MetricSnapshot:
        if self.case.stale:
            raise StaleMetrics("no fresh samples (case)")
        vals = self.case.metrics.get(str(target), {})
        return MetricSnapshot(target=target, observed_at=utcnow(), values={s: vals.get(s) for s in signals})

    def range(self, *a, **k) -> list:
        return []


class RecordingLLM:
    """Passes every request to the model and keeps its whole text (the hard check looks for planted secrets)."""

    def __init__(self, llm: Any):
        self.llm, self.requests, self.calls = llm, [], 0

    def decide(self, messages, tools):
        self.calls += 1
        self.requests.append("\n".join(str(getattr(m, "content", m)) for m in messages))
        return self.llm.decide(messages, tools)


def run_case(case: Case, workdir: Path, llm: Any | None = None, settings: Settings | None = None,
             strategy: str | None = None) -> CaseRun:
    """Replay `case` in a throwaway SQLite store under `workdir`. `llm=None`: no model (classes escalate).
    `strategy`: run every class with this registered strategy instead of the class registry's (the evaluation
    compares strategies on the same cases, §21.2); `None` = as registered."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    db = workdir / f"{case.id}-{os.urandom(3).hex()}.db"
    base = settings or Settings()
    # Pinned whatever the environment says (the worker container says mcp, postgres and has a model key): reads are
    # answered only by the fixtures, the store is a throwaway SQLite file, and no model is built from the environment.
    secrets = workdir / "eval-secrets"            # only a throwaway JWT key: the evaluation serves no HTTP
    secrets.mkdir(exist_ok=True)
    (secrets / "jwt_signing_key").write_text(os.urandom(24).hex(), encoding="utf-8")
    s = dataclasses.replace(base, secrets_dir=secrets, db_path=str(db), db_backend="sqlite",
                            tool_catalogue="direct")
    reg = ExecutorRegistry()
    for kind in EXECUTORS:
        reg.register(kind, lambda url, token, kind=kind: FixtureExecutor(case.fixtures.get(kind, {})))
    rec = RecordingLLM(llm) if llm is not None else None
    hidden = os.environ.pop("OPENAI_API_KEY", None)
    try:
        app = build(s, llm=rec, metrics=CaseMetrics(case), executors=reg, store=SqliteStore(str(db)),
                    require_credentials=False)
    finally:
        if hidden is not None:
            os.environ["OPENAI_API_KEY"] = hidden
    inc = Incident(id=f"inc_eval_{os.urandom(4).hex()}", target=TargetRef.parse(case.target),
                   trigger_kind=TriggerKind.manual, request_kind=RequestKind(case.request), reason=case.reason,
                   principal="evaluation", trigger_id=f"eval:{case.id}", opened_at=utcnow())
    if strategy is not None:
        chosen = app.runner.strategies[strategy]
        for name in list(app.runner.strategies):
            if name != "evidence_pack":            # unsupported / undiagnosable keep the evidence pack
                app.runner.strategies[name] = chosen
    app.store.create_incident(inc, None)
    t0 = time.monotonic()
    done = app.runner.run(inc.id)
    ms = int((time.monotonic() - t0) * 1000)
    evidence = app.store.list_evidence(inc.id)
    audit = app.store.list_for(inc.id)
    passages: list[tuple[str, str]] = []
    for a in audit:
        if a.event == "recall.passages":
            passages = [(p["runbook_id"], p["section"]) for p in (a.detail or {}).get("passages", [])]
    return CaseRun(
        case_id=case.id, outcome=done.outcome.value if done.outcome else None, incident_class=done.incident_class,
        root_cause_target=done.root_cause_target, diagnosis=done.diagnosis, findings=list(done.findings),
        model_calls=rec.calls if rec else 0,
        reads=[(e.capability, e.target, e.status) for e in evidence if e.capability and e.target],
        passages=passages, audit_events=[a.event for a in audit],
        model_requests=rec.requests if rec else [], duration_ms=ms)
