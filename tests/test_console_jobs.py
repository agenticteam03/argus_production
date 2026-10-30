"""ACR-0043 with T-0021 (§12.6): the API never investigates, so the console's reads and write proposals run in the worker.

On vm-095 the API has no executor token and no action path (only the worker has them): a console read from the API
answered `HTTP 401` from the target's read gateway, and a write found no released pair. The API now queues each read
and each write proposal as a `console_job` (migration 022) and waits for the worker's answer; the worker runs it with
its own guarded invoke and action path. A process that has the tools (`argus serve`, these tests' default app) still
runs them in place.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.console.config import ConsoleConfig
from argus.console.jobs import ConsoleJobRunner
from argus.domain.model import Observation, TargetRef, utcnow
from test_console_routes import PRIVATE, login, run, setup, url
from test_console_write_path import CASES, PAIRS, _case, _path
from test_core import incident, make_app  # noqa: F401

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
API = "vm-166/container:argus-lab-api"
WORKER = "vm-166/container:argus-lab-jobworker"


# --- the store (SQLite; tests/test_postgres.py has the same on Postgres) ------------------------------------------
@pytest.fixture
def store(tmp_path):
    return SqliteStore(str(tmp_path / "argus.db"))


def test_a_queued_job_is_claimed_once_oldest_first_and_answered(store):
    store.add_console_job("cjb_2", "read", "inc_1", "olga", {"capability": "container.status"}, NOW)
    store.add_console_job("cjb_1", "read", "inc_1", "olga", {"capability": "container.status", "target": API},
                          NOW - timedelta(seconds=1))

    first = store.claim_console_job("w1", since=NOW - timedelta(minutes=1), at=NOW)
    second = store.claim_console_job("w2", since=NOW - timedelta(minutes=1), at=NOW)

    assert (first["job_id"], first["kind"], first["incident_id"], first["person"]) == ("cjb_1", "read", "inc_1", "olga")
    assert first["request"] == {"capability": "container.status", "target": API}
    assert second["job_id"] == "cjb_2"
    assert store.claim_console_job("w3", since=NOW - timedelta(minutes=1), at=NOW) is None
    assert store.get_console_job("cjb_1")["status"] == "running"

    store.finish_console_job("cjb_1", "done", {"status": "ok"}, NOW)
    assert store.get_console_job("cjb_1") == {"job_id": "cjb_1", "kind": "read", "status": "done",
                                              "result": {"status": "ok"}}
    assert store.get_console_job("cjb_nope") is None


def test_a_job_older_than_the_cutoff_is_never_claimed(store):
    store.add_console_job("cjb_old", "read", "inc_1", "olga", {}, NOW - timedelta(minutes=5))
    assert store.claim_console_job("w1", since=NOW - timedelta(minutes=1), at=NOW) is None
    assert store.get_console_job("cjb_old")["status"] == "queued"


def test_a_console_job_is_never_deleted(store):
    import sqlite3
    store.add_console_job("cjb_1", "read", "inc_1", "olga", {}, NOW)
    with pytest.raises(sqlite3.DatabaseError, match="never deleted"):
        store._q("DELETE FROM console_job")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_console_job("cjb_2", "shell", "inc_1", "olga", {}, NOW)


# --- the API without tools, the worker with them -------------------------------------------------------------------
def observing(app, calls):
    """The worker's guarded invoke, faked: a real Observation, as the real one returns."""
    def invoke(ctx, name, arguments):
        calls.append((name, arguments["target"], ctx.caller, ctx.incident.id))
        target = TargetRef.parse(arguments["target"])
        return Observation(observation_id="obs_1", status="ok", capability=name, target=target, host=target.host,
                           executor="docker_read", collected_at=utcnow(),
                           values={"state": "running", "health": "healthy", "restart_count": 0,
                                   "started_at": "S-START"}, model_text=f"{name} text"), None
    app.runner.invoke = invoke


def no_tools(app):
    """The API as `argus api` builds it (T-0021): no executor token, no action path; any local read is a failure."""
    app.runs_tools = False
    app.runner.action_path = None

    def invoke(*_):
        raise AssertionError("the API ran a read itself")
    app.runner.invoke = invoke


@pytest.fixture
def worker_thread():
    stops = []

    def start(app):
        stop = threading.Event()
        runner = ConsoleJobRunner(app, ConsoleConfig(), idle_s=0.02)
        thread = threading.Thread(target=runner.run_forever, args=(stop,), daemon=True)
        thread.start()
        stops.append((stop, thread))
        return runner
    yield start
    for stop, thread in stops:
        stop.set()
        thread.join(timeout=5)


def test_the_api_without_tools_has_the_worker_run_its_reads(make_app, monkeypatch, worker_thread):  # noqa: F811
    api_app, worker_app = make_app(), make_app()            # one database, two processes
    inc = incident(api_app, API)
    no_tools(api_app)
    calls: list = []
    observing(worker_app, calls)
    client = setup(api_app, monkeypatch)
    worker_thread(worker_app)

    body = run(client, login(client), inc, "worker status").json()

    assert body["status"] == "ok", body
    assert "state=running" in "\n".join(body["output"])
    assert calls == [("container.status", WORKER, "console:olga", inc.id)]
    assert [r["status"] for r in api_app.store.console_history(inc.id)] == ["ok"]


def test_without_a_worker_the_read_fails_with_a_clear_message(make_app, monkeypatch):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    no_tools(app)
    client = setup(app, monkeypatch, ARGUS_CONSOLE_JOB_TIMEOUT_S="0.2")

    body = run(client, login(client), inc, "worker status").json()

    assert body["status"] == "error"
    assert "the worker did not answer" in "\n".join(body["output"])


def test_the_worker_runs_only_the_console_reads(make_app):  # noqa: F811
    app = make_app()
    inc = incident(app, API)
    calls: list = []
    observing(app, calls)
    runner = ConsoleJobRunner(app, ConsoleConfig())
    now = utcnow()
    app.store.add_console_job("cjb_bad", "read", inc.id, "olga",
                              {"capability": "container.restart", "target": WORKER, "arguments": {}}, now)
    app.store.add_console_job("cjb_good", "read", inc.id, "olga",
                              {"capability": "container.status", "target": WORKER, "arguments": {}}, now)

    assert runner.run_once() == "cjb_bad" and runner.run_once() == "cjb_good" and runner.run_once() is None

    bad = app.store.get_console_job("cjb_bad")
    assert bad["status"] == "error" and "not a console read" in bad["result"]["error"]
    good = app.store.get_console_job("cjb_good")
    assert good["status"] == "done" and good["result"]["values"]["state"] == "running"
    assert calls == [("container.status", WORKER, "console:olga", inc.id)]


def test_a_job_for_an_unknown_incident_is_an_error(make_app):  # noqa: F811
    app = make_app()
    runner = ConsoleJobRunner(app, ConsoleConfig())
    app.store.add_console_job("cjb_x", "read", "inc_nope", "olga",
                              {"capability": "container.status", "target": WORKER, "arguments": {}}, utcnow())
    runner.run_once()
    assert app.store.get_console_job("cjb_x")["result"] == {"error": "the incident inc_nope does not exist"}


@pytest.mark.parametrize("text,command,incident_target,incident_class,root_target,runbook,state,live_values",
                         [CASES[1]])
def test_the_api_without_an_action_path_has_the_worker_propose_a_write(
        make_app, monkeypatch, worker_thread, text, command, incident_target, incident_class, root_target,  # noqa: F811
        runbook, state, live_values):
    case = _case(make_app, monkeypatch, text, command, incident_target, incident_class, root_target, runbook, state,
                 live_values)
    worker_app = make_app()                                 # the same database: the worker holds the action path
    path = _path(worker_app, root_target=root_target, live_values=dict(live_values), pairs=set(PAIRS.values()))
    case.app.runs_tools, case.app.runner.action_path = False, None
    worker_thread(worker_app)

    first = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                             json={"input": text}).json()
    assert first["status"] == "needs_confirmation"          # the API checks the released pair from its own policy

    second = case.client.post(url(case.incident, "execute"), headers={**case.auth, **PRIVATE},
                              json={"input": text, "confirmation": "yes"}).json()
    assert second["status"] == "ok" and second["proposal_id"] and second["approval_id"], second
    assert second["judge_verdict"] == "agree"
    proposal = case.app.store.get_action_proposal(second["proposal_id"])
    assert (proposal.input.capability, proposal.input.target) == case.pair
    assert case.app.store.get_action_approval_for_proposal(proposal.id)["state"] == "pending"
    assert path.executor.gateway.calls == []                 # a proposal only: the approval worker acts, later
