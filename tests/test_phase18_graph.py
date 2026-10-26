"""The optional Phase 18 branch shares the incident graph and pauses on a durable answer."""
from __future__ import annotations

from argus.actions.remediation import JudgeResult
from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome
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


def test_judge_doubt_records_recommendation_without_request(app_factory, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    app = app_factory(llm=ScriptedLLM(_diagnose_script), metrics=_metrics())
    path = OfflinePath()
    path.judge = lambda proposal_id: JudgeResult("doubt", reasons=("The ground is uncertain.",))
    app.runner.action_path = path
    inc = incident(app, WORKER_166)
    done = app.runner.run(inc.id)
    assert done.outcome == IncidentOutcome.diagnosed
    assert "request" not in path.calls and "execute" not in path.calls
