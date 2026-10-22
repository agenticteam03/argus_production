"""OP-014 step 9: tests written from the survivors of a second mutation run (fewer workers, so mutants that had timed
out were judged) on `InvokeCapability.__call__`, `_store`, `_finish` and `PolicyEngine.check`.

They pin the audit trail and the stored evidence of the read path (ARCHITECTURE §10, §12.3): which event each outcome
writes, with which rule and detail, and what the evidence record keeps of the observation.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from argus.domain.model import Observation, utcnow
from test_combined_capabilities import API, OTHER, Catalogue, _engine, _invoke

AUDIT_ID = re.compile(r"^aud_[0-9a-f]{16}$")
AT = datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc)


class Rich(Catalogue):
    """Answers with every field an executor can fill, and the status asked for."""

    def __init__(self, status="ok", category="none"):
        super().__init__()
        self.status, self.category = status, category

    def call(self, spec, args, target):
        self.calls.append((spec.name, str(target)))
        return Observation(observation_id=f"obs_{uuid.uuid4().hex[:16]}", status=self.status, capability=spec.name,
                           target=target, host=target.host, executor=spec.executor, collected_at=utcnow(),
                           source_time=AT, duration_ms=12, units={"mem": "bytes"}, partial=True, coverage="2 of 3",
                           identities={"container_id": "abc"}, error_category=self.category, truncated=True,
                           redactions=2, values={"mem": 1}, model_text="mem 1 secret")


class CountingRedactor:
    def value(self, v):
        return v, 0

    def text(self, t):
        return t.replace("secret", "[REDACTED]"), t.count("secret")


def _call(catalogue, name="container.logs", args=None, inventory=True):
    inv, ctx, audit, mem = _invoke(catalogue)
    inv.redactor = CountingRedactor()
    if not inventory:
        inv.inventory = type("I", (), {"target": lambda self, ref: None})()
    obs, ref = inv(ctx, name, {"target": str(API), **(args or {})} if args is not None else {"target": str(API)})
    return obs, ref, audit, mem


def _events(audit):
    return [(a.category, a.event) for a in audit]


# --- a completed read -------------------------------------------------------------------------------------------------

def test_a_completed_read_writes_requested_then_completed_with_its_arguments_and_evidence():
    obs, ref, audit, mem = _call(Rich(), args={"tail": 20})
    assert _events(audit) == [("tool", "tool.requested"), ("tool", "tool.completed")]
    requested, completed = audit
    assert requested.capability == "container.logs" and requested.arguments == {"target": str(API), "tail": 20}
    assert completed.capability == "container.logs" and completed.evidence_id == ref.evidence_id
    assert completed.detail == {"status": "ok", "error_category": "none"}
    assert all(AUDIT_ID.match(a.audit_id) for a in audit)


def test_the_evidence_record_keeps_every_field_of_the_observation():
    obs, ref, audit, mem = _call(Rich())
    rec = mem[-1]
    assert (rec.executor, rec.caller, rec.source_time) == ("docker_read", "model", AT)
    assert (rec.partial, rec.truncated) == (True, True)
    assert rec.values == {"values": {"mem": 1}, "units": {"mem": "bytes"}, "identities": {"container_id": "abc"},
                          "coverage": "2 of 3", "error_category": "none", "duration_ms": 12}
    assert ref.target == str(API) and ref.capability == "container.logs"


def test_the_redactions_of_the_gateway_and_of_this_layer_add_up():
    obs, *_ = _call(Rich())
    assert obs.model_text == "mem 1 [REDACTED]" and obs.redactions == 3          # 2 upstream + 1 here


def test_a_read_that_ran_and_failed_is_recorded_as_failed_not_as_refused():
    obs, ref, audit, mem = _call(Rich(status="error", category="unreachable"))
    assert _events(audit)[-1] == ("tool", "tool.failed")
    assert audit[-1].detail == {"status": "error", "error_category": "unreachable"}


# --- refusals -------------------------------------------------------------------------------------------------------

def test_a_read_with_no_target_is_refused_not_raised():
    inv, ctx, audit, mem = _invoke(Catalogue())
    obs, ref = inv(ctx, "container.status", {})
    assert (obs.status, obs.error_category) == ("refused", "invalid_args")
    assert [(a.event, a.policy_rule) for a in audit][0] == ("tool.refused", "validation")
    assert "error" in audit[0].detail and audit[-1].event == "tool.refused_recorded"


def test_a_target_outside_the_inventory_is_refused_with_the_inventory_rule():
    obs, ref, audit, mem = _call(Catalogue(), name="container.status", inventory=False)
    first = audit[0]
    assert (first.category, first.event, first.policy_rule) == ("tool", "tool.refused", "inventory")
    assert first.detail == {"target": str(API)} and first.capability == "container.status"
    assert audit[-1].event == "tool.refused_recorded"


def test_invalid_arguments_are_refused_with_the_validation_error_and_no_url():
    obs, ref, audit, mem = _call(Catalogue(), args={"tail": 999})
    first = audit[0]
    assert (first.category, first.event, first.policy_rule) == ("tool", "tool.refused", "validation")
    errors = first.detail["error"]
    assert 1 <= len(errors) <= 3 and all("url" not in e for e in errors)
    assert obs.model_text.startswith("REFUSED container.logs: Input should be less than or equal to 200")


def test_invalid_arguments_report_at_most_three_errors():
    many = {f"x{i}": i for i in range(5)}                         # five forbidden extra fields
    obs, ref, audit, mem = _call(Catalogue(), args={"tail": 999, **many})
    assert len(audit[0].detail["error"]) == 3


def test_a_policy_refusal_is_audited_with_the_capability_rule_reason_and_target():
    inv, ctx, audit, mem = _invoke(Catalogue(), scope=(API,))
    obs, ref = inv(ctx, "container.status", {"target": str(OTHER)})
    refused = [a for a in audit if a.event == "tool.refused"][0]
    assert (refused.capability, refused.policy_rule) == ("container.status", "incident_scope")
    assert refused.detail == {"reason": f"{OTHER} is outside this incident's scope", "target": str(OTHER)}
    requested = [a for a in audit if a.event == "tool.requested"][0]
    assert requested.capability == "container.status" and requested.arguments == {"target": str(OTHER)}


# --- the policy engine -------------------------------------------------------------------------------------------------

def test_a_level_above_the_profile_is_refused_by_its_own_rule():
    d = _engine().check(capability="container.status", level=4, safety_class="READ_ONLY_SAFE", target=API,
                        incident_scope={API}, used_in_incident=0)
    assert d.allowed is False and d.rule == "max_tool_level" and d.reason == "level 4 > 3"
