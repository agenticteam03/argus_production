"""OP-014 step 9: tests written from the survivors of the third mutation run (the earlier runs' timeouts re-run with two
workers) on `PolicyEngine.check`, `InvokeCapability.__call__` and `_finish`.

Every decision of the policy names its rule and a reason a reader can act on; an allowed read says which capability
allowed it. An unknown capability is audited as a security event with its name and arguments, and an observation is
never kept without its audit record.
"""
from __future__ import annotations

import yaml

from argus.domain.model import TargetRef
from argus.policy.engine import PolicyEngine
from test_combined_capabilities import API, OTHER, Catalogue, _invoke

HOST = API.host


def _engine(caps=None, **over):
    data = {"profile": "lab", "max_tool_level": 3, "capabilities": caps or {"container.status": {}}, **over}
    return PolicyEngine(data, yaml.safe_dump(data))


def _check(engine, **over):
    kw = dict(capability="container.status", level=1, safety_class="READ_ONLY_SAFE", target=API,
              incident_scope={API}, used_in_incident=0, arguments={})
    return engine.check(**{**kw, **over})


def test_an_allowed_read_names_the_capability_that_allowed_it():
    d = _check(_engine())
    assert (d.allowed, d.rule, d.reason) == (True, "allow:container.status", "allowed")


def test_a_safety_class_outside_the_profile_is_refused_by_its_rule_with_the_profile_named():
    d = _check(_engine(allowed_safety_classes=["READ_ONLY_SAFE"]), safety_class="READ_ONLY_SENSITIVE")
    assert (d.allowed, d.rule, d.reason) == (False, "safety_class", "READ_ONLY_SENSITIVE not allowed in profile lab")


def test_the_incident_budget_defaults_to_ten_and_names_the_count():
    e = _engine()                                                  # no max_per_incident: the default
    assert _check(e, used_in_incident=9).allowed is True
    d = _check(e, used_in_incident=10)
    assert (d.allowed, d.rule, d.reason) == (False, "max_per_incident", "container.status used 10/10")


def test_an_inspection_refusal_carries_the_inspection_policys_reason():
    e = _engine({"host.read_file": {}}, inspection={"targets": {"vm-166/host:vm-166": {"files": ["/var/log/x/"]}}})
    host = TargetRef.parse("vm-166/host:vm-166")
    d = _check(e, capability="host.read_file", target=host, incident_scope={host}, arguments={"path": "/etc/hosts"})
    assert (d.allowed, d.rule) == (False, "inspection")
    assert d.reason == "/etc/hosts is not in the files allowlist of vm-166/host:vm-166"


def test_an_unknown_capability_is_a_security_event_with_its_name_and_arguments():
    inv, ctx, audit, mem = _invoke(Catalogue())
    obs, ref = inv(ctx, "host.exec", {"target": str(API), "cmd": "id"})
    first = audit[0]
    assert (first.category, first.event) == ("security", "security.unknown_or_write_capability")
    assert first.capability == "host.exec" and first.arguments == {"target": str(API), "cmd": "id"}
    assert (obs.status, obs.error_category) == ("refused", "forbidden")
    last = audit[-1]
    assert (last.event, last.capability, last.evidence_id) == ("tool.refused_recorded", "host.exec", ref.evidence_id)
    assert last.detail == {"status": "refused", "error_category": "forbidden"}


def test_an_observation_is_never_kept_without_its_audit_record():
    inv, ctx, audit, mem = _invoke(Catalogue())

    class Failing:
        def __init__(self):
            self.n = 0

        def append(self, record):
            self.n += 1
            if record.event == "tool.completed":
                raise RuntimeError("audit store down")
            audit.append(record)

    inv.audit = Failing()
    obs, ref = inv(ctx, "container.status", {"target": str(API)})
    assert ref is None
    assert (obs.status, obs.error_category, obs.model_text) == (
        "refused", "internal", "REFUSED container.status: audit unavailable")
    assert obs.target == API and obs.host == HOST


# --- refusals keep their own target and say why ------------------------------------------------------------------------

def test_a_bad_target_is_refused_with_the_parse_error_in_the_audit_and_the_text():
    inv, ctx, audit, mem = _invoke(Catalogue())
    obs, ref = inv(ctx, "container.status", {"target": "not a target"})
    first = audit[0]
    assert (first.event, first.policy_rule) == ("tool.refused", "validation")
    assert first.detail["error"] and first.detail["error"] != "None"
    assert obs.model_text.startswith("REFUSED container.status: bad target: ") and obs.target == API


def test_a_target_outside_the_inventory_is_refused_as_itself_with_its_kind_named():
    inv, ctx, audit, mem = _invoke(Catalogue(), scope=(API, OTHER))
    inv.inventory = type("I", (), {"target": lambda self, ref: None if ref == OTHER else object()})()
    obs, ref = inv(ctx, "container.status", {"target": str(OTHER)})
    assert obs.target == OTHER and obs.host == OTHER.host                  # not the incident's target
    assert obs.model_text == f"REFUSED container.status: {OTHER} is not an inventory target of kind ['container']"


def test_invalid_arguments_are_refused_as_the_target_asked_and_audited_with_the_capability():
    inv, ctx, audit, mem = _invoke(Catalogue(), scope=(API, OTHER))
    obs, ref = inv(ctx, "container.logs", {"target": str(OTHER), "tail": 999})
    assert obs.target == OTHER and audit[0].capability == "container.logs"


def test_a_lost_audit_record_refuses_the_read_as_its_own_target():
    inv, ctx, audit, mem = _invoke(Catalogue(), scope=(API, OTHER))

    class Failing:
        def append(self, record):
            if record.event == "tool.completed":
                raise RuntimeError("audit store down")

    inv.audit = Failing()
    obs, ref = inv(ctx, "container.status", {"target": str(OTHER)})
    assert ref is None and obs.target == OTHER and obs.error_category == "internal"


def test_the_policy_sees_the_validated_arguments():
    caps = {"host.read_file": {"max_per_incident": 4}}
    inspection = {"targets": {"vm-166/host:vm-166": {"files": ["/var/log/x/"]}}}
    host = TargetRef.parse("vm-166/host:vm-166")
    inv, ctx, audit, mem = _invoke(Catalogue(), scope=(host,))
    inv.policy = _engine(caps, inspection=inspection)
    obs, ref = inv(ctx, "host.read_file", {"target": str(host), "path": "/var/log/x/app.log"})
    assert obs.status == "ok"                                     # the inspection policy needs the path to allow it
