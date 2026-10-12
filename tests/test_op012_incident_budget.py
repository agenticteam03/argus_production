"""OP-012: `max_per_incident` (config/policy.yaml) holds for the whole incident under the LangGraph runner too.

The graph runner built a fresh `InvocationContext` in every act node, and runs ONE read per graph step, so the
per-capability counters started at zero for every read and the policy limit was never reached. The counters now come
from the incident's evidence in the run state (a read that was refused does not count, as in the plain runner).
"""
from __future__ import annotations

import pytest

from argus.adapters.outbound.llm import ScriptedLLM
from test_core import FakeTargetAgent, incident, make_app  # noqa: F401  (make_app = fixture)
from test_graph_runner import WORKER_166, _metrics

LIMIT = 8                                                   # config/policy.yaml: container.status max_per_incident


def _status_forever(ctx):
    """A model that never concludes: two container.status reads every step."""
    return {"calls": [("get_container_status", {"target": WORKER_166}),
                      ("get_container_status", {"target": WORKER_166})]}


def _status_audit(app, inc_id):
    events = [a for a in app.store.list_for(inc_id) if a.capability == "container.status"]
    done = [a for a in events if a.event in ("tool.completed", "tool.failed")]
    refused = [a for a in events if a.event == "tool.refused" and a.policy_rule == "max_per_incident"]
    return len(done), len(refused)


@pytest.mark.parametrize("runner", ["plain", "langgraph"])
def test_max_per_incident_holds_for_the_whole_incident(make_app, monkeypatch, runner):
    monkeypatch.setenv("ARGUS_RUNNER", runner)
    app = make_app(llm=ScriptedLLM(_status_forever), metrics=_metrics())
    inc = app.runner.run(incident(app, WORKER_166).id)
    done, refused = _status_audit(app, inc.id)
    assert done == LIMIT, f"{runner}: {done} container.status reads executed, the policy allows {LIMIT}"
    assert refused >= 1


def test_the_limit_survives_a_resume(make_app, monkeypatch):
    """The counters come from the checkpointed evidence, not from memory: a resumed run keeps counting."""
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")
    state = {"calls": 0}

    class Crash(BaseException):
        pass

    def script(ctx):
        state["calls"] += 1
        if state["calls"] == 3:
            raise Crash("the worker died mid-investigation")
        return _status_forever(ctx)

    app = make_app(llm=ScriptedLLM(script), metrics=_metrics())
    inc = incident(app, WORKER_166)
    with pytest.raises(Crash):
        app.runner.run(inc.id)
    app.runner.run(inc.id)
    done, refused = _status_audit(app, inc.id)
    assert done == LIMIT and refused >= 1
