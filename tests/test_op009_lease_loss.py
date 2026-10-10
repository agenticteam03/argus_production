"""OP-009: a worker that loses its lease must stop its run (ARCHITECTURE §6.2; found in the after-merge review of #33).

The worker renews its claim while a run lasts. A renewal that fails (a database error) is retried until the lease
has really expired; a lost claim (renew_claim False, or the lease expired while retrying) cancels the run. The
runner checks the cancel signal between nodes and before every read: it stops, audits `incident.claim_lost` and
writes no final status, so the worker that now owns the incident resumes it from its checkpoint.
"""
from __future__ import annotations

import threading
import time

import pytest

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, IncidentStatus
from argus.infrastructure.worker import Worker
from test_core import FakeTargetAgent, _nodes, incident, make_app  # noqa: F401  (make_app = fixture)
from test_graph_runner import WORKER_166, _diagnose_script, _metrics

T = "vm-095/container:argus-lab-worker"


class CancelAwareRunner:
    """Stands in for the investigation runner: runs for a while and reports whether it was cancelled."""

    def __init__(self, seconds=0.0):
        self.seconds, self.cancelled = seconds, None

    def run(self, incident_id, cancel=None):
        deadline = time.monotonic() + self.seconds
        while time.monotonic() < deadline and not (cancel is not None and cancel.is_set()):
            time.sleep(0.02)
        self.cancelled = cancel is not None and cancel.is_set()


# --- the runner stops at the next node -------------------------------------------------------------
@pytest.mark.parametrize("runner", ["plain", "langgraph"])
def test_a_lost_claim_stops_the_run_before_the_next_read_and_records_nothing(make_app, monkeypatch, runner):
    monkeypatch.setenv("ARGUS_RUNNER", runner)
    cancel = threading.Event()

    def script(ctx):                       # the claim is lost while the model decides its first reads
        cancel.set()
        return _diagnose_script(ctx)

    app = make_app(llm=ScriptedLLM(script), metrics=_metrics())
    inc = incident(app, WORKER_166)
    app.runner.run(inc.id, cancel=cancel)

    after = app.store.get_incident(inc.id)
    events = [a.event for a in app.store.list_for(inc.id)]
    assert len(FakeTargetAgent.calls) == 0                     # the read it asked for was not made
    assert "incident.claim_lost" in events
    assert "incident.recorded" not in events                   # no final status written
    assert after.outcome is None and after.status == IncidentStatus.running
    assert "record" not in _nodes(app, inc.id)


def test_the_new_owner_resumes_a_cancelled_graph_run(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    cancel = threading.Event()
    state = {"first": True}

    def script(ctx):
        if state["first"]:
            state["first"] = False
            cancel.set()
        return _diagnose_script(ctx)

    app = make_app(llm=ScriptedLLM(script), metrics=_metrics())
    inc = incident(app, WORKER_166)
    app.runner.run(inc.id, cancel=cancel)                      # the old worker stops
    done = app.runner.run(inc.id)                              # the worker that took the claim back
    assert done.outcome == IncidentOutcome.diagnosed
    assert "incident.resumed" in [a.event for a in app.store.list_for(inc.id)]


def test_a_run_without_a_cancel_signal_is_unchanged(make_app, monkeypatch):
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = make_app(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    done = app.runner.run(incident(app, WORKER_166).id)
    assert done.outcome == IncidentOutcome.diagnosed


# --- the worker decides when the claim is lost -----------------------------------------------------
def test_a_renewal_that_fails_once_is_retried_and_the_run_keeps_its_lease(make_app):
    app = make_app()
    incident(app, T)
    app.runner = CancelAwareRunner(seconds=0.6)
    real, calls = app.store.renew_claim, []

    def flaky(*a, **k):
        calls.append(a)
        if len(calls) == 1:
            raise RuntimeError("database briefly unavailable")
        return real(*a, **k)

    app.store.renew_claim = flaky
    Worker(app, worker_id="w1", lease_s=2, renew_every_s=0.1).run_once()
    assert len(calls) >= 3                                     # the renewer survived the failure
    assert app.runner.cancelled is False


def test_a_lost_claim_cancels_the_run(make_app):
    app = make_app()
    incident(app, T)
    app.runner = CancelAwareRunner(seconds=5)
    app.store.renew_claim = lambda *a, **k: False              # another worker owns it now
    started = time.monotonic()
    Worker(app, worker_id="w1", lease_s=2, renew_every_s=0.1).run_once()
    assert app.runner.cancelled is True
    assert time.monotonic() - started < 2                      # it did not run to the end


def test_renewals_failing_until_the_lease_expires_cancel_the_run(make_app):
    app = make_app()
    incident(app, T)
    app.runner = CancelAwareRunner(seconds=5)

    def down(*a, **k):
        raise RuntimeError("database down")

    app.store.renew_claim = down
    started = time.monotonic()
    Worker(app, worker_id="w1", lease_s=1, renew_every_s=0.1).run_once()
    elapsed = time.monotonic() - started
    assert app.runner.cancelled is True
    assert 0.9 <= elapsed < 3                                  # cancelled once the lease (1 s) was really gone


def test_a_failing_renewer_cancels_at_the_lease_expiry_not_at_its_next_attempt(make_app):
    """Review of PR #53: with renewals failing, the run is cancelled when the lease expires, not up to one renewal
    interval later (lease 1 s, attempts every 0.7 s: before the fix the cancel came at 1.4 s)."""
    app = make_app()
    incident(app, T)
    app.runner = CancelAwareRunner(seconds=5)

    def down(*a, **k):
        raise RuntimeError("database down")

    app.store.renew_claim = down
    started = time.monotonic()
    Worker(app, worker_id="w1", lease_s=1, renew_every_s=0.7).run_once()
    elapsed = time.monotonic() - started
    assert app.runner.cancelled is True
    assert 0.9 <= elapsed < 1.25, elapsed
