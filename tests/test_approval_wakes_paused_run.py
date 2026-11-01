"""An approved action starts within seconds of the answer, not when the worker's claim expires (inc_6a4980a4d8ed).

A run paused at an interrupt is parked: the worker clears `claimed_by` and keeps `claimed_until` at the pending
approval's expiry. The approval's answer requeues only a parked run, in the transaction that records the answer; a
run answered while it is still live is requeued by the worker right after it parks. In production on 2026-10-30 the
approval waited 3 min 42 s for the claim to expire.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from argus.actions.remediation import freeze_proposal
from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, IncidentStatus, utcnow
from argus.infrastructure.worker import Worker
from test_core import incident, make_app as app_factory  # noqa: F401
from test_graph_runner import WORKER_166, _diagnose_script, _metrics
from test_phase18_graph import OfflinePath
from test_phase18_remediation import candidate


class RowPath(OfflinePath):
    """The offline action path on the store's real approval rows: the answer goes through answer_action_approval."""

    def __init__(self, store, incident_id):
        super().__init__()
        self.store, self.incident_id, self.clock, self.on_first_look = store, incident_id, utcnow, None

    def request(self, proposal_id):
        self.calls.append("request")
        now = utcnow()
        self.proposal = freeze_proposal(candidate(incident_id=self.incident_id), at=now)
        self.store.add_action_proposal(self.proposal)
        self.store.add_judge_verdict(self.proposal.id, "test-judge", {
            "verdict": "agree", "risk": "green", "reasons": [], "checks": {}, "proposal_digest": self.proposal.digest,
        }, now)
        self.store.add_action_approval("appr_wake", self.proposal.id, self.proposal.digest, now,
                                       self.proposal.expires_at)
        return "appr_wake"

    def approval_state(self, approval_id):            # as OfflineActionPath.approval_state
        self.calls.append("approval_state")
        row = self.store.get_action_approval(approval_id)
        if self.on_first_look is not None:            # a person answers while the run is still live
            hook, self.on_first_look = self.on_first_look, None
            hook()
        expires = datetime.fromisoformat(row["expires_at"])  # SQLite keeps the time as text
        return "expired" if row["state"] == "pending" and self.clock() >= expires else row["state"]

    def respond(self, decision):
        return self.store.answer_action_approval("appr_wake", self.proposal.digest, "operator", decision, utcnow())


def _parked(app_factory, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = app_factory(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    inc = incident(app, WORKER_166)
    path = RowPath(app.store, inc.id)
    app.runner.action_path = path
    return app, inc, path


def _claim(app, incident_id):
    return app.store._q("SELECT status, claimed_by, claimed_until FROM incident WHERE id=?", (incident_id,))[0]


def test_a_paused_run_is_parked_until_its_approval_expires(app_factory, monkeypatch):  # noqa: F811
    app, inc, path = _parked(app_factory, monkeypatch)
    w = Worker(app, worker_id="w1", lease_s=300)
    assert w.run_once() == inc.id
    assert "execute" not in path.calls
    status, by, until = _claim(app, inc.id)
    assert (status, by) == ("running", None)                     # parked: no live worker holds it
    assert until == path.proposal.expires_at.isoformat()         # an unanswered approval still ends at its expiry
    assert w.recover() == 0                                      # not requeued before it is woken or it expires
    assert app.store.requeue_expired(now=path.proposal.expires_at - timedelta(seconds=1)) == 0
    assert w.run_once() is None


def test_an_approval_wakes_the_parked_run_and_the_action_runs(app_factory, monkeypatch):  # noqa: F811
    app, inc, path = _parked(app_factory, monkeypatch)
    w = Worker(app, worker_id="w1", lease_s=300)
    w.run_once()
    assert path.respond("approved")
    assert _claim(app, inc.id) == ("queued", None, None)         # requeued by the answer itself: no recover tick
    assert app.store.get_incident(inc.id).status == IncidentStatus.queued
    assert w.run_once() == inc.id                                # the worker's next poll (idle_s) resumes it
    done = app.store.get_incident(inc.id)
    assert done.outcome == IncidentOutcome.recovered_verified and path.calls.count("execute") == 1


def test_an_answer_while_the_run_is_live_leaves_its_claim_and_the_worker_requeues_it(app_factory, monkeypatch):  # noqa: F811
    app, inc, path = _parked(app_factory, monkeypatch)
    seen = {}

    def answer_now():
        seen["before"] = _claim(app, inc.id)
        assert path.respond("approved")
        seen["after"] = _claim(app, inc.id)
    path.on_first_look = answer_now                              # the run read "pending" and is about to pause
    w = Worker(app, worker_id="w1", lease_s=300)
    assert w.run_once() == inc.id
    assert seen["before"][1] == "w1" and seen["after"] == seen["before"]     # a live run's claim is never touched
    assert _claim(app, inc.id) == ("queued", None, None)         # requeued as soon as it parked
    assert w.run_once() == inc.id
    assert app.store.get_incident(inc.id).outcome == IncidentOutcome.recovered_verified
    assert path.calls.count("execute") == 1


def test_a_denial_wakes_the_run_and_it_ends_denied(app_factory, monkeypatch):  # noqa: F811
    app, inc, path = _parked(app_factory, monkeypatch)
    w = Worker(app, worker_id="w1", lease_s=300)
    w.run_once()
    assert path.respond("denied")
    assert w.run_once() == inc.id
    done = app.store.get_incident(inc.id)
    assert done.outcome == IncidentOutcome.denied and done.status == IncidentStatus.escalated
    assert "execute" not in path.calls


def test_an_unanswered_approval_resumes_at_its_expiry_and_ends_expired(app_factory, monkeypatch):  # noqa: F811
    app, inc, path = _parked(app_factory, monkeypatch)
    w = Worker(app, worker_id="w1", lease_s=300)
    w.run_once()
    after = path.proposal.expires_at + timedelta(seconds=1)
    path.clock = lambda: after
    assert app.store.requeue_expired(now=after) == 1             # the recover tick after the expiry
    assert w.run_once() == inc.id
    done = app.store.get_incident(inc.id)
    assert done.outcome == IncidentOutcome.expired and done.status == IncidentStatus.escalated
    assert "execute" not in path.calls


def test_a_changed_precondition_after_the_wake_still_refuses_the_action(app_factory, monkeypatch):  # noqa: F811
    """inc_6a4980a4d8ed: the cache was started by hand meanwhile; the fresh precheck refuses, correctly."""
    app, inc, path = _parked(app_factory, monkeypatch)

    def changed(approval_id):
        path.calls.append("precheck")
        raise RuntimeError("incident, detector or action precondition changed")
    path.precheck = changed
    w = Worker(app, worker_id="w1", lease_s=300)
    w.run_once()
    path.respond("approved")
    assert w.run_once() == inc.id
    done = app.store.get_incident(inc.id)
    assert done.outcome == IncidentOutcome.no_action_escalated and "execute" not in path.calls


def test_an_answer_never_requeues_a_run_another_worker_holds(app_factory, monkeypatch):  # noqa: F811
    app, inc, path = _parked(app_factory, monkeypatch)
    w = Worker(app, worker_id="w1", lease_s=300)
    w.run_once()
    app.store._q("UPDATE incident SET claimed_by='w2' WHERE id=?", (inc.id,))   # resumed meanwhile by w2
    assert path.respond("approved")
    assert _claim(app, inc.id)[:2] == ("running", "w2")


def test_a_lost_claim_is_not_parked(app_factory, monkeypatch):  # noqa: F811
    app, inc, path = _parked(app_factory, monkeypatch)
    app.store.renew_claim = lambda *a, **k: False                # another worker owns it now
    w = Worker(app, worker_id="w1", lease_s=300, renew_every_s=0.0)
    assert w.run_once() == inc.id
    assert _claim(app, inc.id)[1] == "w1"                       # left for the lease to expire, as before


def test_a_paused_verification_is_parked_for_one_lease(app_factory, monkeypatch):  # noqa: F811
    app, inc, path = _parked(app_factory, monkeypatch)
    path.verify = lambda action_id: None                         # no fresh sample yet: the run pauses in verify
    w = Worker(app, worker_id="w1", lease_s=300)
    w.run_once()
    path.respond("approved")
    before = utcnow()
    w.run_once()
    status, by, until = _claim(app, inc.id)
    assert (status, by) == ("running", None)                     # no approval waits: no wake, one lease as before
    assert timedelta(seconds=290) < datetime.fromisoformat(until) - before < timedelta(seconds=310)


def test_the_worker_checks_for_expired_claims_every_five_seconds_by_default(monkeypatch):
    import argus.__main__ as main
    seen = {}

    class Captured:
        def __init__(self, app, **kw):
            seen.update(kw)

        def run_forever(self, stop):
            pass
    monkeypatch.setattr(main, "Worker", Captured)
    monkeypatch.setattr(main, "build", lambda *a, **k: object())
    monkeypatch.setattr(main, "_close_tracing", lambda app: None)
    monkeypatch.setattr(main.signal, "signal", lambda *a: None)
    main.worker()
    assert seen["recover_every_s"] == 5.0
    monkeypatch.setenv("ARGUS_WORKER_RECOVER_S", "2")
    main.worker()
    assert seen["recover_every_s"] == 2.0
    assert Worker(object()).recover_every_s == 5.0
