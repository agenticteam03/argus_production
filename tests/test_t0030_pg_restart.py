"""T-0030 (phase 13): a database restart is a pause, never a crash (ARCHITECTURE §6.2; IMPLEMENTATION_PLAN phase 13).

While Postgres restarts, every store call fails. The scheduler already survives it (its tick and its reconciliation
are guarded); the worker's loop did not: an error from `recover()` or from claiming the next incident ended
`run_forever`, and the container had to be restarted by Docker. Now the worker logs it, waits and tries again; when
the database is back it claims and runs the queued incident.
"""
from __future__ import annotations

import threading
import time

from argus.infrastructure.worker import Worker
from test_core import incident, make_app  # noqa: F401  (make_app = fixture)
from test_worker_loop import SlowRunner, T


class DatabaseDown(Exception):
    """What psycopg raises while the server restarts (an OperationalError); any exception behaves the same."""


def _down_for(store, method: str, calls: int):
    real, state = getattr(store, method), {"left": calls}

    def flaky(*a, **k):
        if state["left"] > 0:
            state["left"] -= 1
            raise DatabaseDown("server closed the connection unexpectedly")
        return real(*a, **k)
    setattr(store, method, flaky)
    return state


def _run_until(w, stop, cond, seconds=5.0):
    t = threading.Thread(target=w.run_forever, args=(stop,))
    t.start()
    try:
        deadline = time.monotonic() + seconds
        while not cond() and time.monotonic() < deadline:
            time.sleep(0.05)
        return t.is_alive()
    finally:
        stop.set()
        t.join(timeout=2)


def test_the_worker_survives_a_database_that_is_down_while_it_claims(make_app):
    app = make_app()
    inc = incident(app, T)
    app.runner = SlowRunner()
    state = _down_for(app.store, "claim_next_queued", 3)
    w = Worker(app, worker_id="w1", idle_s=0.05, recover_every_s=60, db_retry_s=0.05)
    alive = _run_until(w, threading.Event(), lambda: inc.id in app.runner.ran)
    assert state["left"] == 0 and alive                    # three failures absorbed, the loop still running
    assert app.runner.ran == [inc.id]                      # the database came back: the incident was claimed and run


def test_the_worker_survives_a_database_that_is_down_at_start(make_app):
    app = make_app()
    inc = incident(app, T)
    app.runner = SlowRunner()
    _down_for(app.store, "requeue_expired", 2)             # recover() is the first call of run_forever
    w = Worker(app, worker_id="w1", idle_s=0.05, recover_every_s=0.1, db_retry_s=0.05)
    assert _run_until(w, threading.Event(), lambda: inc.id in app.runner.ran)
    assert app.runner.ran == [inc.id]


def test_a_database_error_is_logged_and_retried_after_a_pause(make_app, caplog):
    app = make_app()
    app.runner = SlowRunner()
    _down_for(app.store, "claim_next_queued", 1)
    w = Worker(app, worker_id="w1", idle_s=0.05, recover_every_s=60, db_retry_s=0.3)
    started = time.monotonic()
    stop = threading.Event()
    t = threading.Thread(target=w.run_forever, args=(stop,))
    t.start()
    time.sleep(0.15)
    stop.set()
    t.join(timeout=2)
    assert not t.is_alive() and time.monotonic() - started < 1      # stop still ends the pause at once
    assert any("database" in r.getMessage() and "retry" in r.getMessage() for r in caplog.records)
