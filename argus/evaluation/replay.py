"""Replay one case through the real wiring with fixture executors and a fixed metric snapshot."""
from __future__ import annotations

import dataclasses
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.capabilities.spec import ExecutorError
from argus.domain.model import Incident, MetricSnapshot, RequestKind, TargetRef, TriggerKind, utcnow
from argus.evaluation.cases import Case
from argus.infrastructure.wiring import Settings, build, load_anomaly_inputs, read_signals
from argus.ports.ports import StaleMetrics
from argus.tooling.executors import ExecutorRegistry

EXECUTORS = ("docker_read", "host_probe", "network_probe", "db_probe", "prometheus")

# The target service's named log patterns (services/target/service.py, not in the agent image); a test keeps them equal.
LOG_PATTERNS = {
    "error": re.compile(r"(?i)(error|exception)s?\b|\b(traceback|fatal|panic)\b"),
    "timeout": re.compile(r"(?i)\b(timed? ?out|timeout|deadline exceeded)\b"),
    "refused": re.compile(r"(?i)\b(connection refused|refused|unreachable|no route to host)\b"),
    "oom": re.compile(r"(?i)\b(out of memory|oom|cannot allocate memory|memoryerror)\b"),
    "disk_full": re.compile(r"(?i)\b(no space left on device|disk full|enospc)\b"),
    "auth": re.compile(r"(?i)\b(unauthori[sz]ed|forbidden|authentication failed|permission denied)\b"),
    "restart": re.compile(r"(?i)\b(starting|started|shutting down|shutdown|terminated|sigterm|exiting)\b"),
}
LOG_ROUTES = ("logs", "logs_window", "search")


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
    # T-0019 batch 2: why each invalid decision was refused (`decision.invalid` alone hid a 7-in-a-row loop)
    invalid_decisions: list[str] = field(default_factory=list)
    duration_ms: int = 0
    trial: int = 1
    # ACR-0024 §3.8 (T-0047 H4): the final decision's hypotheses (`incident_hypothesis`), by rank, as
    # {id, target, cause_class, status, rank, chosen}; whether the chosen one is not first; the H1 checks' problems
    hypotheses: list[dict] = field(default_factory=list)
    ranking_disagrees: bool = False
    hypothesis_problems: list[str] = field(default_factory=list)
    # targets with an `ok` observation or metric snapshot, or named in the values of an `ok` observation on their host
    # (the database's sessions name the leaking client) (`unsupported_root_cause`); None = not recorded
    observed: list[str] | None = None


class FixtureExecutor:
    """Answers a read from the case: `fixtures["path?k=v"]` (its parameters, sorted), else `fixtures[path]`, else
    `fixtures["*"]`; `{error: <category>}` fails the read, as the target service would. A container's long log,
    `/containers/<name>/log` {lines}, answers its `logs`, `logs_window` and `search` routes as the gateway does."""

    def __init__(self, answers: dict[str, Any], lines: dict | None = None, class_signals: dict | None = None):
        self.answers = answers
        self.lines, self.class_signals = lines or {}, class_signals or {}       # T-0047 H5, as PrometheusClient

    def get(self, path: str, params: dict | None = None) -> Any:
        keyed = path + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
        if params and keyed in self.answers:            # a per-parameter answer (e.g. /dns?name=argus-lab-backend)
            answer = self.answers[keyed]
        elif path in self.answers:
            answer = self.answers[path]
        elif self._derived(path, params or {}) is not None:
            answer = self._derived(path, params or {})
        elif "*" in self.answers:
            answer = self.answers["*"]
        else:
            raise ExecutorError("not_found", f"{path}: not found")       # as a target service says it
        if isinstance(answer, dict) and set(answer) == {"error"}:
            raise ExecutorError(str(answer["error"]), f"{path}: {answer['error']}")
        if isinstance(answer, dict) and answer.get("collected_at"):
            # EVAL-offers: collected now, as the snapshot and the histories (a fixed fixture date read as a week-old
            # sample beside them); the case's own answer is not changed
            answer = {**answer, "collected_at": utcnow().isoformat()}
        return answer

    def _derived(self, path: str, params: dict) -> dict | None:
        return self._connectivity(params) if path == "/connectivity" else self._from_log(path, params)

    def _connectivity(self, params: dict) -> dict | None:
        """EVAL-offers: `/connectivity` from the two containers' status fixtures, as the gateway builds it from their
        inspect (Docker's `Running` is true while running, restarting or paused); a side without status: None."""
        sides = {}
        for role in ("from", "to"):
            name = str(params.get(role) or "")
            st = self.answers.get(f"/containers/{name}/status")
            if not name or not isinstance(st, dict):
                return None
            sides[role] = {"name": name, "running": str(st.get("state")) in ("running", "restarting", "paused"),
                           "networks": sorted(st.get("networks") or [])}
        return {**sides, "shared": sorted(set(sides["from"]["networks"]) & set(sides["to"]["networks"])),
                "collected_at": None}

    def _from_log(self, path: str, params: dict) -> dict | None:
        """EVAL-offers: the gateway's log routes over the case's long log (`_window_logs` keeps at most 500 lines)."""
        base, _, route = path.rpartition("/")
        log = self.answers.get(base + "/log") if route in LOG_ROUTES else None
        if not isinstance(log, dict):
            return None
        lines = [str(x) for x in log.get("lines") or []]
        window, cut = lines[-500:], len(lines) > 500
        if route == "logs":
            tail = max(1, min(200, int(params.get("tail", 50))))
            return {"lines": lines[-tail:], "truncated": False, "collected_at": None}
        minutes = int(params.get("minutes", 30))
        if route == "logs_window":
            return {"lines": window, "minutes": minutes, "stream": params.get("stream", "both"), "truncated": cut,
                    "collected_at": None}
        pattern = LOG_PATTERNS.get(str(params.get("pattern")))
        if pattern is None:
            return None
        hits = [ln for ln in window if pattern.search(ln)]
        return {"pattern": params["pattern"], "matched": len(hits), "lines": hits[-50:], "minutes": minutes,
                "truncated": cut or len(hits) > 50, "collected_at": None}

    def range(self, signal: str, target: TargetRef, minutes: int, step_s: int, end_offset_s: int = 0,
              **params) -> list[tuple[float, float]]:
        """Metric history (the prometheus executor): `fixtures.prometheus.range.<signal>` as [seconds before now,
        value] pairs, cut to the window asked; none = no samples (the capability answers NO DATA, unknown). A window
        ending `end_offset_s` ago (T-0038) reads `range_earlier.<offset>.<signal>`, [seconds before that end, value];
        never the current series (EVAL-offers: "now" and "earlier" were the same points)."""
        now = time.time()
        if end_offset_s:
            earlier = (self.answers.get("range_earlier") or {})
            series = earlier.get(int(end_offset_s)) or earlier.get(str(int(end_offset_s))) or {}
            points = series.get(signal) or []
            now -= int(end_offset_s)
        else:
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

    def dependency_probes(self, target) -> dict:
        return {}


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
    lines, class_signals = load_anomaly_inputs(base.config_dir, set(read_signals(base.config_dir)))   # T-0047 H5
    for kind in EXECUTORS:
        reg.register(kind, lambda url, token, kind=kind: FixtureExecutor(case.fixtures.get(kind, {}),
                                                                         lines, class_signals))
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
    rows = app.store.hypotheses(inc.id)
    final = [r for r in rows if r["step"] == max(x["step"] for x in rows)] if rows else []
    hypotheses = [{"id": r["hypothesis_id"], "target": r["target"], "cause_class": r["cause_class"],
                   "status": r["status"], "rank": r["rank"], "chosen": r["chosen"]} for r in final]
    passages: list[tuple[str, str]] = []
    for a in audit:
        if a.event == "recall.passages":
            passages = [(p["runbook_id"], p["section"]) for p in (a.detail or {}).get("passages", [])]
    result = CaseRun(
        case_id=case.id, outcome=done.outcome.value if done.outcome else None, incident_class=done.incident_class,
        root_cause_target=done.root_cause_target, diagnosis=done.diagnosis, findings=list(done.findings),
        model_calls=rec.calls if rec else 0,
        reads=[(e.capability, e.target, e.status) for e in evidence if e.capability and e.target],
        passages=passages, audit_events=[a.event for a in audit],
        model_requests=rec.requests if rec else [], duration_ms=ms,
        invalid_decisions=[f"{(a.detail or {}).get('reason')}: {str((a.detail or {}).get('detail'))[:300]}"
                           for a in audit if a.event == "decision.invalid"],
        hypotheses=hypotheses, ranking_disagrees=any(h["chosen"] and h["rank"] != 1 for h in hypotheses),
        hypothesis_problems=[p for a in audit if a.event == "hypothesis.invalid"
                             for p in (a.detail or {}).get("problems") or []],
        observed=_observed(evidence, [t.ref for t in app.inventory.targets()]))
    _drop_store(app, db)
    return result


def _observed(evidence: list, refs: list[TargetRef]) -> list[str]:
    """The targets the run observed: those of its `ok` observations and metric snapshots, and the inventory targets an
    `ok` observation on the same host names in its values."""
    ok = [e for e in evidence if e.target and e.status == "ok" and e.kind in ("observation", "metric_snapshot")]
    seen = {e.target for e in ok}
    for e in ok:
        if e.kind == "observation":
            values = json.dumps(e.values, default=str)
            seen |= {str(r) for r in refs if e.target.startswith(f"{r.host}/")
                     and re.search(rf"(?<![\w-]){re.escape(r.name)}(?![\w-])", values)}
    return sorted(seen)


def _drop_store(app: Any, db: Path) -> None:
    """The run's store is throwaway: remove it once its result is read (EVAL-2: 275 runs filled eval-run.sh's 64 MiB
    /tmp and the CLI died at run 274). Best effort: a file still open elsewhere stays for the folder's own cleanup."""
    conn = getattr(app.store, "_db", None)
    if conn is not None:
        conn.close()
    for f in db.parent.glob(db.name + "*"):                     # the database and its -wal / -shm files
        try:
            f.unlink()
        except OSError:
            pass
