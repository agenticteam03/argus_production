"""T-0014 step 2: `argus worker` and `argus api` are separate programs (ARCHITECTURE §3, §6.2).

The worker recovers only expired claims at start, claims one incident at a time, renews its claim while the run
lasts, survives a failing run, and stops cleanly. The api serves requests and never investigates.
"""
from __future__ import annotations

import threading
import time

import pytest

from argus.domain.model import IncidentStatus
from argus.infrastructure.worker import Worker
from test_core import incident, make_app  # noqa: F401  (make_app = fixture)

T = "vm-095/container:argus-lab-worker"


class SlowRunner:
    """Stands in for the investigation runner: records what it ran, can take a while or fail."""

    def __init__(self, seconds=0.0, fail_on=()):
        self.seconds, self.fail_on, self.ran = seconds, set(fail_on), []

    def run(self, incident_id, cancel=None):   # OP-009: the worker passes its lost-claim signal
        self.ran.append(incident_id)
        time.sleep(self.seconds)
        if incident_id in self.fail_on:
            raise RuntimeError("the run failed")


def test_run_once_claims_the_oldest_and_runs_it(make_app):
    app = make_app()
    first, second = incident(app, T), incident(app, T)
    app.runner = SlowRunner()
    w = Worker(app, worker_id="w1")
    assert w.run_once() == first.id
    assert w.run_once() == second.id
    assert w.run_once() is None
    assert app.runner.ran == [first.id, second.id]


def test_the_worker_renews_its_claim_while_a_run_lasts(make_app):
    app = make_app()
    incident(app, T)
    app.runner = SlowRunner(seconds=0.5)
    renewals = []
    real = app.store.renew_claim
    app.store.renew_claim = lambda *a, **k: renewals.append(a) or real(*a, **k)
    Worker(app, worker_id="w1", lease_s=2, renew_every_s=0.1).run_once()
    assert len(renewals) >= 3 and all(r[1] == "w1" for r in renewals)


def test_start_recovers_only_expired_claims(make_app):
    app = make_app()
    live, stale = incident(app, T), incident(app, T)
    app.store.claim_next_queued("other-worker", lease_s=300)                      # live: another worker holds it
    app.store.claim_next_queued("dead-worker", lease_s=300)
    app.store._q("UPDATE incident SET claimed_until=NULL WHERE id=?", (stale.id,))  # its worker died long ago
    Worker(app, worker_id="w1").recover()
    assert app.store.get_incident(live.id).status == IncidentStatus.running
    assert app.store.get_incident(stale.id).status == IncidentStatus.queued


def test_a_running_worker_takes_back_a_claim_that_expires_later(make_app):
    """T-0014 step 5 (found before the VM test): Docker restarts a crashed worker within seconds, while the dead
    worker's lease is still live, so recovering only at start would leave that run `running` forever. The worker
    re-checks for expired claims while it runs."""
    app = make_app()
    orphan = incident(app, T)
    app.store.claim_next_queued("dead-worker", lease_s=1)                         # its worker dies right now
    app.runner = SlowRunner()
    stop = threading.Event()
    w = Worker(app, worker_id="w2", idle_s=0.05, recover_every_s=0.2)
    assert w.recover() == 0                                                       # at start the lease is still live
    t = threading.Thread(target=w.run_forever, args=(stop,))
    t.start()
    try:
        deadline = time.monotonic() + 5
        while orphan.id not in app.runner.ran and time.monotonic() < deadline:
            time.sleep(0.05)
        assert app.runner.ran == [orphan.id]                                      # taken back once it expired, and run
    finally:
        stop.set()
        t.join(timeout=2)


def test_a_failing_run_does_not_stop_the_worker(make_app):
    app = make_app()
    bad, good = incident(app, T), incident(app, T)
    app.runner = SlowRunner(fail_on={bad.id})
    w = Worker(app, worker_id="w1")
    assert w.run_once() == bad.id
    assert w.run_once() == good.id


def test_stop_ends_the_loop_and_claims_nothing_new(make_app):
    app = make_app()
    app.runner = SlowRunner()
    stop = threading.Event()
    w = Worker(app, worker_id="w1", idle_s=0.05)
    t = threading.Thread(target=w.run_forever, args=(stop,))
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2)
    assert not t.is_alive()
    inc = incident(app, T)
    assert app.store.get_incident(inc.id).status == IncidentStatus.queued and app.runner.ran == []


def test_the_commands_exist():
    from argus.__main__ import build_parser
    p = build_parser()
    for cmd in ("serve", "api", "worker"):
        assert p.parse_args([cmd]).cmd == cmd


def test_api_serves_without_a_worker(monkeypatch):
    import uvicorn

    import argus.__main__ as m
    started = []
    monkeypatch.setattr(m, "build", lambda: object())
    monkeypatch.setattr("argus.adapters.inbound.http.build_api", lambda app: "api")
    monkeypatch.setattr("argus.adapters.inbound.http.build_webhook", lambda app: "webhook")
    monkeypatch.setattr(uvicorn, "Config", lambda app, **kw: app)
    monkeypatch.setattr(uvicorn.Server, "__init__", lambda self, cfg: setattr(self, "cfg", cfg))

    async def serve(self):
        started.append(self.cfg)
    monkeypatch.setattr(uvicorn.Server, "serve", serve)
    monkeypatch.setattr(m, "Worker", lambda *a, **k: pytest.fail("the api must not run a worker"))
    m.api()
    assert started == ["api", "webhook"]
