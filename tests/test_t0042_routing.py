"""T-0042: escalation routing as data (ARCHITECTURE §15.2, `config/routing.yaml`).

Every escalation already enqueues a notification (`<incident>:escalation`, the outbox). It now says WHERE it goes: per
unsupported alert name first, then per class family, else the default (the operators' channel). A target is
`channel:<name>` or `peer:<name>` (§23). The file is validated at startup: an unknown family or a malformed target
refuses it, as every other data file.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from argus.domain.model import IncidentOutcome
from argus.policy.routing import Routing
from test_core import FakeMetrics, ScriptedLLM, incident, make_app  # noqa: F401  (make_app = fixture)

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {"availability", "database", "dependency", "platform", "saturation", "stability"}


def test_the_shipped_file_sends_everything_to_the_operators_channel():
    r = Routing.from_data(yaml.safe_load((ROOT / "config" / "routing.yaml").read_text(encoding="utf-8")), FAMILIES)
    assert r.default == "channel:operators"
    assert r.target(family="database", alertname=None) == "channel:operators"
    assert r.target(family=None, alertname="SomethingUnknown") == "channel:operators"


def test_alert_name_first_then_family_then_default():
    r = Routing.from_data({"default": "channel:operators", "by_family": {"database": "channel:dba"},
                           "by_alertname": {"KafkaLag": "peer:streaming-agent"}}, FAMILIES)
    assert r.target(family="database", alertname="KafkaLag") == "peer:streaming-agent"
    assert r.target(family="database", alertname=None) == "channel:dba"
    assert r.target(family="saturation", alertname="Other") == "channel:operators"


@pytest.mark.parametrize("data", [
    {"default": "operators"},                                              # no kind
    {"default": "channel:operators", "by_family": {"made_up": "channel:x"}},   # unknown family
    {"default": "channel:operators", "by_alertname": {"A": "email:x"}},        # unknown kind
    {"default": "channel:operators", "extra": 1},                              # unknown key
    {"by_family": {}},                                                         # no default
])
def test_a_bad_file_is_refused(data):
    with pytest.raises(ValueError):
        Routing.from_data(data, FAMILIES)


def test_an_escalation_notification_names_its_route(make_app):
    app = make_app(llm=ScriptedLLM([]), metrics=FakeMetrics({"vm-095/container:argus-lab-worker": {"restarts_10m": 0}}))
    inc = app.runner.run(incident(app, "vm-095/container:argus-lab-worker").id)
    assert inc.outcome == IncidentOutcome.unsupported_escalated
    note = next(n for n in app.store.notifications() if n["key"] == f"{inc.id}:escalation")
    assert note["payload"]["route"] == "channel:operators"


def test_the_route_of_a_class_follows_its_family(make_app):
    app = make_app()
    app.runner.routing = Routing.from_data({"default": "channel:operators",
                                            "by_family": {"stability": "channel:sre"}}, FAMILIES)
    assert app.runner._route(type("I", (), {"id": "x", "incident_class": "container_restart_loop"})()) == "channel:sre"
    assert app.runner._route(type("I", (), {"id": "x", "incident_class": None})()) == "channel:operators"
