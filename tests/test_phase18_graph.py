"""The optional Phase 18 branch shares the incident graph and pauses on a durable answer."""
from __future__ import annotations

from argus.actions.remediation import JudgeResult
from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, IncidentStatus
from test_core import incident, make_app as app_factory  # noqa: F401
from test_graph_runner import WORKER_166, _diagnose_script, _metrics


class OfflinePath:
    def __init__(self):
        self.answer = "pending"
        self.calls = []

    def propose(self, inc, state):
        self.calls.append("propose")
        return "prop_test"

    def judge(self, proposal_id):
        self.calls.append("judge")
        return JudgeResult.agree("digest_test")

    def request(self, proposal_id):
        self.calls.append("request")
        return "appr_test"

    def approval_state(self, approval_id):
        self.calls.append("approval_state")
        return self.answer

    def precheck(self, approval_id):
        self.calls.append("precheck")

    def execute(self, approval_id):
        self.calls.append("execute")
        return {"id": "act_test", "state": "confirmed"}

    def verify(self, action_id):
        self.calls.append("verify")
        return "recovered_verified"


def test_graph_pauses_without_answer_and_resumes_from_frozen_ids(app_factory, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = app_factory(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    path = OfflinePath()
    app.runner.action_path = path
    inc = incident(app, WORKER_166)
    paused = app.runner.run(inc.id)
    assert paused.outcome is None and paused.status == "running"
    assert "execute" not in path.calls
    path.answer = "approved"  # in the real offline path this comes from the durable approval row
    done = app.runner.run(inc.id)
    assert done.outcome == IncidentOutcome.recovered_verified
    assert path.calls.count("execute") == 1


def test_judge_disagreement_keeps_the_diagnosis_and_escalates_without_request(app_factory, monkeypatch):  # noqa: F811
    """The cause is found but nothing was done: the problem is still there, so the incident is not closed."""
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = app_factory(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    path = OfflinePath()
    path.judge = lambda proposal_id: JudgeResult("disagree", reasons=("The cause is elsewhere.",), risk="amber")
    path.held_back = lambda incident_id: path.calls.append(("held_back", incident_id))
    app.runner.action_path = path
    inc = incident(app, WORKER_166)
    done = app.runner.run(inc.id)
    assert done.outcome == IncidentOutcome.diagnosed and done.status == IncidentStatus.escalated
    assert done.diagnosis.endswith("The proposed action was not sent for approval: the judge answered disagree.")
    assert ("held_back", inc.id) in path.calls
    assert "request" not in path.calls and "execute" not in path.calls
    sent = {n["key"]: n["payload"] for n in app.store.notifications()}
    assert sent[f"{inc.id}:escalation"]["outcome"] == "diagnosed"


def test_judge_doubt_goes_to_a_person_with_the_raised_colour(app_factory, monkeypatch):  # noqa: F811
    """ACR-0039: a doubt is not a stop. The approval is requested, the person decides, and the audit says the doubt
    was sent to them."""
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = app_factory(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    path = OfflinePath()
    path.judge = lambda proposal_id: JudgeResult("doubt", reasons=("The ground is uncertain.",), risk="amber")
    app.runner.action_path = path
    inc = incident(app, WORKER_166)
    app.runner.run(inc.id)
    assert "request" in path.calls and ("held_back", inc.id) not in path.calls
    [sent] = [r[1] for r in app.store.audit_chain() if r[1]["event"] == "judge.doubt_sent_to_approver"]
    assert sent["detail"] == {"proposal_id": "prop_test", "risk": "amber"}


def test_a_refused_approval_request_escalates_too(app_factory, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = app_factory(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    path = OfflinePath()
    path.request = lambda proposal_id: None
    app.runner.action_path = path
    done = app.runner.run(incident(app, WORKER_166).id)
    assert done.status == IncidentStatus.escalated and "the approval request was refused" in done.diagnosis


def test_the_executed_action_and_its_verification_are_on_the_incidents_audit_with_the_approver(app_factory, monkeypatch):  # noqa: F811
    """S4 left no audit line for the execution: the incident did not say an operator approved a restart."""
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = app_factory(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    path = OfflinePath()
    path.answer = "approved"
    path.approved_action = lambda approval_id: {"approval_id": approval_id, "approved_by": "operator1",
                                                "capability": "container.restart", "target": WORKER_166}
    app.runner.action_path = path
    inc = incident(app, WORKER_166)
    app.runner.run(inc.id)
    lines = {a.event: a.detail for a in app.store.list_for(inc.id)}
    assert lines["action.executed"] == {"approval_id": "appr_test", "approved_by": "operator1",
                                        "capability": "container.restart", "target": WORKER_166,
                                        "action_id": "act_test", "state": "confirmed"}
    assert lines["action.verified"] == {"action_id": "act_test", "outcome": "recovered_verified"}


def test_a_failing_approver_lookup_never_stops_the_action(app_factory, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = app_factory(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    path = OfflinePath()
    path.answer = "approved"
    app.runner.action_path = path                          # OfflinePath has no approved_action: the lookup fails
    done = app.runner.run(incident(app, WORKER_166).id)
    assert done.outcome == IncidentOutcome.recovered_verified
    assert {a.event: a.detail for a in app.store.list_for(done.id)}["action.executed"]["approval_id"] == "appr_test"
