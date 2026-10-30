"""CON-4b (ACR-0043 section 3, spec section 8): Argus's comment after each console command, wired end to end.

A fake MetricsPort, a fake model and a fake clock (nothing sleeps): the analysis is stored per command, the evidence is
appended to the incident, the ranking is recomputed by the deterministic `rank()`, and the history route carries the
`analysis` the UI reads. The command's own answer never waits for it."""
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from argus.adapters.inbound.http import build_api
from argus.console.parser import parse
from argus.domain.model import EvidenceRecord, utcnow
from test_console_routes import PRIVATE, fake_invoke, login, run, url
from test_core import incident, make_app  # noqa: F401

from pwdlib import PasswordHash

API = "vm-166/container:argus-lab-api"
CACHE = "vm-166/container:argus-lab-cache"
PASSWORD = "a-long-password"


class Clock:
    """Real time plus an offset that only `sleep` moves: no test waits."""

    def __init__(self):
        self.offset = 0.0

    def now(self):
        return utcnow() + timedelta(seconds=self.offset)

    def sleep(self, seconds):
        self.offset += seconds


class ScriptedMetrics:
    def __init__(self):
        self.missing, self.calls = False, 0

    def snapshot(self, target, signals):
        self.calls += 1
        values = {s: (None if self.missing else 0.02) for s in signals}
        return SimpleNamespace(target=target, observed_at=None if self.missing else utcnow(), values=values)


class FakeModel:
    """Answers from the sources it is given, like a model that cites them; `fail` raises."""

    def __init__(self):
        self.fail, self.calls = False, 0

    def decide(self, messages, tools):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model down")
        payload = json.loads(messages[1].content)
        refs = [s["reference"] for s in payload["sources"]]
        cpu = next(r for r in refs if r.startswith("after:container_cpu_cores:"))
        out0 = next(r for r in refs if r.startswith("output:"))
        reply = {"evidence": [{"hypothesis_id": "h2", "effect": "contradicts", "reference": cpu,
                               "reason": "The API CPU did not change when its errors began."}],
                 "comment_sentences": [{"text": "The API CPU stayed flat while its errors rose", "reference": cpu},
                                       {"text": "So CPU is not what broke the API", "reference": out0}],
                 "suggestion": "cache status",
                 "ranking": [{"id": "h2", "rank": 1}]}                 # the model does not rank: this must be ignored
        return SimpleNamespace(text=json.dumps(reply))


class InlinePool:
    """Holds the jobs the service starts; `run_all` runs them (the command's answer has already gone)."""

    def __init__(self):
        self.jobs = []

    def submit(self, fn, *args):
        self.jobs.append((fn, args))

    def run_all(self):
        jobs, self.jobs = self.jobs, []
        for fn, args in jobs:
            fn(*args)


def seed_hypotheses(app, inc):
    """The cache scenario: H2 (the API's CPU, the red herring) leads H1 (the cache) before the console."""
    now = utcnow()
    for evidence_id, kind, target in (("ev_h1", "metric_snapshot", CACHE), ("ev_h2", "observation", API)):
        app.store.append_evidence(EvidenceRecord(
            evidence_id=evidence_id, incident_id=inc.id, kind=kind, capability="metrics.snapshot", target=target,
            host="vm-166", executor="x", caller="model", source_time=None, collected_at=now, status="ok",
            values={}, model_text=evidence_id).with_hash())
    rows = [("h1", "The cache stopped, so the API cannot reach it", CACHE, "dependency", ["ev_h1"], 2.0, 2),
            ("h2", "The API is saturated on CPU", API, "self", ["ev_h2"], 3.0, 1)]
    app.store.add_hypotheses(inc.id, 1, [
        {"hypothesis_id": i, "statement": s, "cause_class": "other", "target": t, "relation": rel,
         "status": "supported", "support_ids": sup, "against_ids": [], "score": score, "rank": rank, "chosen": i == "h2"}
        for i, s, t, rel, sup, score, rank in rows], now)


@pytest.fixture
def ctx(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    seed_hypotheses(app, inc)
    clock, metrics, model, pool = Clock(), ScriptedMetrics(), FakeModel(), InlinePool()
    app.metrics, app.analysis_model = metrics, model
    calls: list = []
    fake_invoke(app, calls=calls)
    monkeypatch.setenv("ARGUS_OPERATOR_CONSOLE", "1")
    monkeypatch.setenv("ARGUS_CONSOLE_ANALYSIS", "1")
    app.settings.ops_peer = "testclient"
    password = PasswordHash.recommended().hash(PASSWORD)
    app.store.upsert_principal("olga", "human", "operator", ["lab"], password)
    app.store.upsert_principal("vera", "human", "viewer", ["lab"], password)
    api = build_api(app)
    service = api.state.console
    service.analysis.now, service.analysis.sleep, service.analysis.pool = clock.now, clock.sleep, pool
    client = TestClient(api)
    return SimpleNamespace(app=app, inc=inc, client=client, auth=login(client), clock=clock, metrics=metrics,
                           model=model, pool=pool, service=service)


def history(ctx):
    return ctx.client.get(url(ctx.inc, "history"), headers={**ctx.auth, **PRIVATE}).json()["entries"]


def entry_of(ctx, command_id):
    return next(e for e in history(ctx) if e["command_id"] == command_id)


def test_execute_answers_at_once_and_the_analysis_waits_in_the_background(ctx):
    got = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()

    assert got["status"] == "ok" and "analysis" not in got
    assert len(ctx.pool.jobs) == 1 and ctx.clock.offset == 0 and ctx.model.calls == 0        # nothing ran, nothing slept
    assert entry_of(ctx, got["command_id"])["analysis"]["status"] == "analyzing"            # a read has no settle delay


def test_a_read_stores_a_done_analysis_with_a_grounded_comment_and_the_history_carries_it(ctx):
    command_id = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"]
    ctx.pool.run_all()

    analysis = entry_of(ctx, command_id)["analysis"]

    assert analysis["status"] == "done" and analysis["retryable"] is False
    assert analysis["comment"] == "The API CPU stayed flat while its errors rose. So CPU is not what broke the API."
    assert set(analysis) == {"status", "comment", "evidence", "ranking", "retryable", "suggestion"}
    assert analysis["suggestion"]["command"] == "cache status" and analysis["suggestion"]["command_id"] == "cache.status"
    assert analysis["suggestion"]["id"].startswith("sug_")
    (change,) = analysis["evidence"]
    assert (change["hypothesis_id"], change["effect"]) == ("h2", "contradicts")
    assert ctx.metrics.calls >= 4                                   # before, then two samples after, of two targets
    stored = ctx.app.store.console_analyses(ctx.inc.id)[command_id]
    assert len(stored["before"]["samples"]) == 2 and len(stored["after"]) == 2


def test_the_red_herring_is_demoted_only_by_the_deterministic_ranking(ctx):
    command_id = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"]
    ctx.pool.run_all()

    ranking = {r["id"]: r for r in entry_of(ctx, command_id)["analysis"]["ranking"]}

    assert (ranking["h1"]["rank"], ranking["h2"]["rank"]) == (1, 2)             # the model's own "ranking" was ignored
    assert ranking["h2"]["counted_against"] == 1 and ranking["h2"]["score"] == 1.0   # 3 for it, 2 against it: rank()
    rows = ctx.app.store.hypotheses(ctx.inc.id)
    latest = [r for r in rows if r["step"] == 2]
    assert {r["hypothesis_id"]: r["rank"] for r in latest} == {"h1": 1, "h2": 2}
    h2 = next(r for r in latest if r["hypothesis_id"] == "h2")
    assert h2["against_ids"] == [change["evidence_id"] for change in entry_of(ctx, command_id)["analysis"]["evidence"]]
    assert [r["rank"] for r in rows if r["step"] == 1 and r["hypothesis_id"] == "h2"] == [1]   # history is kept


def test_the_evidence_is_appended_to_the_incident_once(ctx):
    command_id = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"]
    ctx.pool.run_all()
    evidence_id = entry_of(ctx, command_id)["analysis"]["evidence"][0]["evidence_id"]

    (record,) = ctx.app.store.get_evidence([evidence_id])

    assert record.incident_id == ctx.inc.id and record.capability == "operator_console"
    assert record.kind == "metric_snapshot" and record.target == API and record.caller == "console:olga"
    assert "container_cpu_cores" in record.model_text
    assert len([r for r in ctx.app.store.list_evidence(ctx.inc.id) if r.evidence_id == evidence_id]) == 1


def test_a_write_command_waits_its_settle_delay_before_it_analyses(ctx):
    parsed = parse("cache restart")
    now = ctx.clock.now()
    row = {"command_id": "cmd_aaaa0001", "incident_id": ctx.inc.id, "person": "olga", "input": "cache restart",
           "command": "cache.restart", "cls": "write", "status": "ok", "output": "container.start ok",
           "output_truncated": False, "suggestion_id": None, "started_at": now, "finished_at": now}
    ctx.app.store.add_console_command(row)
    runner = ctx.service.analysis
    runner.submit(row, parsed, runner.before(parsed, ctx.inc), "olga")
    stored = ctx.app.store.console_analyses(ctx.inc.id)["cmd_aaaa0001"]

    waiting = runner.view(row, stored, now + timedelta(seconds=20))
    assert (waiting["status"], waiting["countdown_s"], waiting["retryable"]) == ("waiting", 25, False)
    assert waiting["settle_until"] == (now + timedelta(seconds=45)).astimezone().astimezone(now.tzinfo).isoformat()
    assert runner.view(row, stored, now + timedelta(seconds=44.5))["countdown_s"] == 1
    assert runner.view(row, stored, now + timedelta(seconds=45))["status"] == "analyzing"

    ctx.pool.run_all()

    assert ctx.clock.offset >= 45                                   # the job slept the settle delay, then sampled
    done = runner.view(row, ctx.app.store.console_analyses(ctx.inc.id)["cmd_aaaa0001"])
    assert done["status"] == "done"


def test_a_model_failure_is_an_error_with_no_comment_and_changes_nothing(ctx):
    ctx.model.fail = True
    got = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()
    ctx.pool.run_all()

    analysis = entry_of(ctx, got["command_id"])["analysis"]

    assert analysis["status"] == "error" and analysis["retryable"] is True and analysis["message"]
    assert "comment" not in analysis and "evidence" not in analysis
    assert got["status"] == "ok" and entry_of(ctx, got["command_id"])["status"] == "ok"      # the command is unchanged
    assert max(r["step"] for r in ctx.app.store.hypotheses(ctx.inc.id)) == 1                  # no ranking refresh
    assert [r for r in ctx.app.store.list_evidence(ctx.inc.id) if r.capability == "operator_console"] == []


def test_without_a_model_the_analysis_says_so_and_never_makes_up_a_comment(ctx):
    ctx.app.analysis_model = None
    got = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()
    ctx.pool.run_all()

    analysis = entry_of(ctx, got["command_id"])["analysis"]

    assert analysis["status"] == "error" and analysis["retryable"] is False and "comment" not in analysis


def test_metrics_missing_for_60_seconds_is_a_retryable_error_and_recheck_fixes_it(ctx):
    ctx.metrics.missing = True
    command_id = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"]
    ctx.pool.run_all()

    failed = entry_of(ctx, command_id)["analysis"]
    assert (failed["status"], failed["message"], failed["retryable"]) == ("error", "Metrics not available yet", True)
    assert ctx.clock.offset >= 60 - 15 and ctx.model.calls == 0

    ctx.metrics.missing = False
    again = ctx.client.post(url(ctx.inc, f"commands/{command_id}/recheck"), headers={**ctx.auth, **PRIVATE})

    assert again.status_code == 202 and again.json()["command_id"] == command_id
    assert again.json()["analysis"]["status"] == "analyzing"       # answered at once; the job has not run
    ctx.pool.run_all()
    fixed = entry_of(ctx, command_id)["analysis"]
    assert fixed["status"] == "done" and fixed["comment"]
    assert any(r.event == "console.recheck" for r in ctx.app.store.audit_since(
        utcnow() - timedelta(hours=1), ("console.recheck",)))


def test_recheck_is_409_when_not_retryable_404_when_unknown(ctx):
    command_id = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"]
    ctx.pool.run_all()
    headers = {**ctx.auth, **PRIVATE}

    assert ctx.client.post(url(ctx.inc, f"commands/{command_id}/recheck"), headers=headers).status_code == 409
    assert ctx.client.post(url(ctx.inc, "commands/cmd_00000000/recheck"), headers=headers).status_code == 404
    assert ctx.client.post(url(ctx.inc, "commands/not-a-command/recheck"), headers=headers).status_code == 404
    assert ctx.client.post(url("inc_nope", f"commands/{command_id}/recheck"), headers=headers).status_code == 404


def test_recheck_follows_the_other_console_routes_rules(ctx):
    command_id = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"]
    path = url(ctx.inc, f"commands/{command_id}/recheck")

    assert ctx.client.post(path, headers={**login(ctx.client, "vera"), **PRIVATE}).status_code == 403    # a viewer
    assert ctx.client.post(path, headers=ctx.auth).status_code == 404                                    # public path
    assert ctx.client.post(path, headers=PRIVATE).status_code == 401


def test_meta_commands_and_refusals_have_no_analysis(ctx):
    ids = [run(ctx.client, ctx.auth, ctx.inc, text).json()["command_id"] for text in ("help", "history", "status; rm")]

    assert ctx.pool.jobs == []
    assert all("analysis" not in entry_of(ctx, i) for i in ids)


def test_the_analysis_can_be_switched_off(ctx, monkeypatch):
    monkeypatch.setenv("ARGUS_CONSOLE_ANALYSIS", "0")
    api = build_api(ctx.app)
    api.state.console.analysis.pool = ctx.pool
    client = TestClient(api)

    got = run(client, login(client), ctx.inc, "api cpu").json()

    assert got["status"] == "ok" and ctx.pool.jobs == [] and ctx.metrics.calls == 0
    assert ctx.app.store.console_analyses(ctx.inc.id) == {}


def test_a_job_that_sleeps_never_holds_a_worker_slot_so_many_reads_all_reach_done(ctx):
    """TASK-123: with 2 workers, 5 reads in a row: every job reaches its sleep (none waits for another's) and all finish."""
    import threading

    from argus.console.analysis_runner import DaemonPool

    gate, sleepers, lock = threading.Event(), [], threading.Lock()

    def sleep(seconds):
        with lock:
            sleepers.append(seconds)
        assert gate.wait(10)                            # the shared fake clock is not moved: five sleeps would pass 60 s

    analysis = ctx.service.analysis
    analysis.pool, analysis.sleep = DaemonPool(), sleep
    ids = [run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"] for _ in range(5)]

    deadline = threading.Event()
    for _ in range(200):
        with lock:
            if len(sleepers) == 5:
                break
        deadline.wait(0.05)
    with lock:
        assert len(sleepers) == 5                       # all five asleep at once: the 2 slots were free the whole time
    gate.set()
    for _ in range(200):
        if all(entry_of(ctx, i)["analysis"]["status"] == "done" for i in ids):
            break
        deadline.wait(0.05)
    assert [entry_of(ctx, i)["analysis"]["status"] for i in ids] == ["done"] * 5


def test_two_quick_rechecks_start_one_job(ctx):
    ctx.metrics.missing = True
    command_id = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"]
    ctx.pool.run_all()
    ctx.metrics.missing = False
    target = url(ctx.inc, f"commands/{command_id}/recheck")

    first = ctx.client.post(target, headers={**ctx.auth, **PRIVATE})
    second = ctx.client.post(target, headers={**ctx.auth, **PRIVATE})

    assert (first.status_code, second.status_code) == (202, 409)
    assert len(ctx.pool.jobs) == 1


def test_a_step_taken_by_the_investigation_meanwhile_is_retried_not_a_failed_analysis(ctx):
    real, calls = ctx.app.store.add_hypotheses, []

    def conflict_once(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 1:
            raise RuntimeError("UNIQUE constraint failed: hypotheses.incident_id, step, hypothesis_id")
        return real(*args, **kwargs)

    ctx.app.store.add_hypotheses = conflict_once
    command_id = run(ctx.client, ctx.auth, ctx.inc, "api cpu").json()["command_id"]
    ctx.pool.run_all()

    assert entry_of(ctx, command_id)["analysis"]["status"] == "done"
    assert len(calls) == 2
