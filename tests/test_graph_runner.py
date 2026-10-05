"""T-0013: the v1.8 skeleton as a LangGraph graph with a checkpointer (Phase 9, first slice).

The graph must behave exactly like the plain runner (same nodes, same outcomes) and must resume an interrupted
investigation from its last checkpoint without repeating completed reads.
"""
from __future__ import annotations

import pytest

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, RequestKind
from test_core import FakeMetrics, FakeTargetAgent, _nodes, incident, make_app  # noqa: F401  (make_app = fixture)

WORKER_166 = "vm-166/container:argus-lab-worker"
WORKER_095 = "vm-095/container:argus-lab-worker"


class Crash(BaseException):
    """Simulates the process dying (not an Exception: the runner must not record it as an outcome)."""


def _diagnose_script(ctx):
    if "container.status" not in ctx:
        return {"calls": [("get_container_status", {"target": WORKER_166})]}
    ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
    return {"calls": [("conclude", {"diagnosis": "OOM-killed by its own 64 MiB limit", "evidence_ids": ids[-1:],
                                    "confidence": "high", "root_cause_target": WORKER_166})]}


def _metrics(stale=False):
    return FakeMetrics({WORKER_166: {"restarts_10m": 5, "oom_killed": 1, "last_exit_code": 137},
                        WORKER_095: {"restarts_10m": 0}}, stale=stale)


SCENARIOS = {
    "diagnosed": (WORKER_166, RequestKind.report, False),
    "healthy": (WORKER_095, RequestKind.check, False),
    "unsupported": (WORKER_095, RequestKind.report, False),
    "undiagnosable": (WORKER_166, RequestKind.report, True),
    "refused": ("vm-166/container:not-in-inventory", RequestKind.report, False),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_graph_runner_takes_the_same_path_as_the_plain_runner(make_app, monkeypatch, name):
    target, kind, stale = SCENARIOS[name]
    results = {}
    for runner in ("plain", "langgraph"):
        monkeypatch.setenv("ARGUS_RUNNER", runner)
        app = make_app(llm=ScriptedLLM(_diagnose_script), metrics=_metrics(stale))
        inc = app.runner.run(incident(app, target, kind).id)
        results[runner] = (_nodes(app, inc.id), inc.outcome, inc.root_cause_target)
    assert type(app.runner).__name__ == "GraphRunner"
    assert results["langgraph"] == results["plain"]


def test_graph_runner_resumes_after_a_crash_without_repeating_reads(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    state = {"crashed": False}

    def script(ctx):
        if "container.status" in ctx and not state["crashed"]:
            state["crashed"] = True
            raise Crash("the worker process died after the first read")
        return _diagnose_script(ctx)

    app = make_app(llm=ScriptedLLM(script), metrics=_metrics())
    inc = incident(app, WORKER_166)
    with pytest.raises(Crash):
        app.runner.run(inc.id)
    reads_before = len(FakeTargetAgent.calls)
    assert reads_before >= 1                                   # the read happened before the crash

    done = app.runner.run(inc.id)                              # e.g. the worker's recovery loop after a restart
    assert done.outcome == IncidentOutcome.diagnosed
    assert len(FakeTargetAgent.calls) == reads_before          # the completed read was not repeated
    assert _nodes(app, inc.id) == ["detect", "recall", "investigate", "act", "investigate", "record"]
    assert "incident.resumed" in [a.event for a in app.store.list_for(inc.id)]


def test_runner_switch(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_RUNNER", "plain")
    assert type(make_app().runner).__name__ == "SkeletonRunner"
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    assert type(make_app().runner).__name__ == "GraphRunner"
    monkeypatch.setenv("ARGUS_RUNNER", "something-else")
    with pytest.raises(SystemExit):
        make_app()


def test_checkpoint_migration_covers_every_library_migration():
    """002_checkpoints.sql creates LangGraph's checkpoint schema for the runtime role (no DDL at runtime). If a library
    upgrade adds a schema migration, this fails: write the next deploy/migrations/00N file instead of guessing."""
    import re
    from pathlib import Path
    from langgraph.checkpoint.postgres.base import BasePostgresSaver
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "migrations" / "002_checkpoints.sql").read_text(encoding="utf-8")
    m = re.search(r"INSERT INTO checkpoint_migrations \(v\) VALUES ([^;]+);", sql)
    assert m, "002 must record the library migrations it covers"
    covered = {int(v) for v in re.findall(r"\((\d+)\)", m.group(1))}
    assert covered == set(range(len(BasePostgresSaver.MIGRATIONS)))
    assert "CONCURRENTLY" not in sql                           # db-migrate.sh runs each file in one transaction
    assert "DELETE" not in re.findall(r"GRANT ([A-Z, ]+) ON checkpoint", sql)[0]


# --- review finding (conantkd): a crash in the middle of a node must not repeat the reads already completed ----------
def _die_on_call(monkeypatch, n: int):
    """The n-th executor call (1-based) kills the process once, before it reads anything."""
    real, seen = FakeTargetAgent.get, {"count": 0, "died": False}

    def get(self, path, params=None):
        seen["count"] += 1
        if seen["count"] == n and not seen["died"]:
            seen["died"] = True
            raise Crash(f"process died before read {n}")
        return real(self, path, params)
    monkeypatch.setattr(FakeTargetAgent, "get", get)


def test_resume_inside_act_does_not_repeat_completed_reads(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")

    def script(ctx):                                           # one step with TWO reads, then conclude
        if "container.status" not in ctx:
            return {"calls": [("get_container_status", {"target": WORKER_166}),
                              ("get_container_logs", {"target": WORKER_166})]}
        return _diagnose_script(ctx)

    app = make_app(llm=ScriptedLLM(script), metrics=_metrics())
    inc = incident(app, WORKER_166)
    _die_on_call(monkeypatch, 2)                               # dies between the first and the second read
    with pytest.raises(Crash):
        app.runner.run(inc.id)
    done = app.runner.run(inc.id)
    assert done.outcome == IncidentOutcome.diagnosed
    paths = [p for _, p in FakeTargetAgent.calls]
    assert paths.count("/containers/argus-lab-worker/status") == 1    # completed before the crash: not repeated
    assert paths.count("/containers/argus-lab-worker/logs") == 1      # interrupted: done once, after the resume


def test_resume_inside_evidence_pack_does_not_repeat_completed_reads(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = make_app(llm=ScriptedLLM([]), metrics=_metrics())
    inc = incident(app, WORKER_095)                            # healthy metrics + a report -> evidence pack
    _die_on_call(monkeypatch, 3)
    with pytest.raises(Crash):
        app.runner.run(inc.id)
    done = app.runner.run(inc.id)
    assert done.outcome == IncidentOutcome.unsupported_escalated
    assert len(FakeTargetAgent.calls) == len(set(FakeTargetAgent.calls)) >= 3   # every read exactly once
