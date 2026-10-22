"""OP-014 step 9: tests written from the survivors of a mutation run (mutmut 3.3.1) on `argus/policy/` and
`argus/application/invoke_capability.py`, the code that enforces the read path and the rails.

Each test pins a property a mutant could change without any other test failing: what a refused read and an audit
record carry, the fields a combined capability's result keeps (§12.7), what a refused sub-read records, and an
absolute deny pattern with a wildcard.
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone

from argus.capabilities.spec import CapabilityResult
from argus.policy.inspection import InspectionPolicy
from argus.domain.model import TargetRef
from test_combined_capabilities import API, HOST, Catalogue, _fake_combined, _invoke

COMBINED = "analysis.fake_combined"
OBS_ID = re.compile(r"^obs_[0-9a-f]{16}$")


class CountingRedactor:
    """Replaces the word `secret` and says how many it replaced, like the real redactor."""

    def value(self, v):
        return v, 0

    def text(self, t):
        return (t or "").replace("secret", "[REDACTED]"), (t or "").count("secret")


def _combined(impl, **over):
    return replace(_fake_combined([]), impl=impl, **over)


def _run(spec, redactor=None):
    cat = Catalogue({COMBINED: spec})
    inv, ctx, audit, mem = _invoke(cat)
    if redactor is not None:
        inv.redactor = redactor
    obs, ref = inv(ctx, COMBINED, {"target": str(API)})
    return obs, ref, audit, mem, inv


# --- a refused read and its audit record ----------------------------------------------------------------------------

def test_a_refused_read_names_no_executor_and_falls_back_to_the_incident_target():
    inv, ctx, audit, _ = _invoke(Catalogue())
    obs, ref = inv(ctx, "container.nope", {"target": str(API)})
    assert (obs.status, obs.executor, obs.error_category) == ("refused", "none", "forbidden")
    assert (obs.target, obs.host) == (API, "vm-166")                 # no target given: the incident's
    assert obs.model_text == "REFUSED container.nope: unknown or non-read capability"
    assert OBS_ID.match(obs.observation_id) and ref.evidence_id == obs.observation_id


def test_every_audit_record_carries_the_incident_the_caller_and_the_policy_version():
    inv, ctx, audit, _ = _invoke(Catalogue())
    inv(ctx, "container.nope", {"target": str(API)})
    assert audit and all(a.incident_id == "inc_combined" for a in audit)
    assert all(a.actor == "model" and a.policy_version == inv.policy.version for a in audit)
    assert inv.policy.version


# --- a combined capability's result (§12.7) ---------------------------------------------------------------------------

def test_the_impl_gets_the_validated_arguments():
    seen = []

    def impl(args, target, info, invoker):
        seen.append(args)
        return CapabilityResult(values={}, model_text="ok")

    spec = _combined(impl)
    _run(spec)
    assert len(seen) == 1 and isinstance(seen[0], spec.args_model)


def test_a_failing_impl_is_an_internal_error_that_keeps_its_sub_reads():
    def impl(args, target, info, invoker):
        invoker.read("container.status", API)
        raise RuntimeError("boom")

    spec = _combined(impl)
    obs, ref, audit, mem, _ = _run(spec)
    assert (obs.status, obs.error_category) == ("error", "internal")
    assert obs.model_text == f"{COMBINED} on {API}: error (RuntimeError)"
    assert (obs.capability, obs.target, obs.host, obs.executor) == (COMBINED, API, "vm-166", spec.executor)
    assert OBS_ID.match(obs.observation_id)
    assert len(obs.values["subcalls"]) == 1 and obs.values["subcall_refs"][0]["capability"] == "container.status"
    assert [a.event for a in audit][-1] == "tool.failed"


def test_the_result_keeps_the_impls_status_units_times_coverage_and_counts_its_redactions():
    at = datetime(2026, 10, 22, 5, 0, tzinfo=timezone.utc)

    def impl(args, target, info, invoker):
        return CapabilityResult(values={"n": 1}, status="error", error_category="unreachable", units={"n": "bytes"},
                                source_time=at, partial=True, coverage="1 of 2 parts",
                                model_text="secret here and secret there")

    obs, *_ = _run(_combined(impl), redactor=CountingRedactor())
    assert (obs.status, obs.error_category) == ("error", "unreachable")
    assert (obs.units, obs.source_time, obs.partial, obs.coverage) == ({"n": "bytes"}, at, True, "1 of 2 parts")
    assert obs.model_text == "[REDACTED] here and [REDACTED] there" and obs.redactions == 2


def test_a_combined_capability_with_allowed_fields_keeps_only_those_and_names_the_rest():
    def impl(args, target, info, invoker):
        invoker.read("container.status", API)
        return CapabilityResult(values={"kept": 1, "extra": 2}, model_text="ok")

    obs, ref, audit, *_ = _run(_combined(impl, allowed_fields=("kept", "subcalls")))
    assert obs.values == {"kept": 1, "subcalls": obs.values["subcalls"]} and len(obs.values["subcalls"]) == 1
    assert obs.dropped_fields == ["extra", "subcall_refs"]
    assert audit[-1].detail["dropped_fields"] == ["extra", "subcall_refs"]


def test_without_allowed_fields_nothing_is_dropped():
    def impl(args, target, info, invoker):
        return CapabilityResult(values={"kept": 1, "extra": 2}, model_text="ok")

    obs, *_ = _run(_combined(impl, allowed_fields=None))
    assert obs.values["extra"] == 2 and obs.dropped_fields == []


# --- a refused sub-read ------------------------------------------------------------------------------------------------

def test_a_refused_sub_read_is_audited_with_its_rule_target_and_combined_capability():
    spec = _fake_combined([("container.status", API, {})] * 3)                 # max_subcalls 2
    obs, ref, audit, mem, _ = _run(spec)
    refused = [a for a in audit if a.event == "tool.refused" and a.policy_rule == "max_subcalls"]
    assert len(refused) == 1
    assert refused[0].capability == "container.status"
    assert refused[0].detail == {"reason": f"{COMBINED} may read 2 times", "target": str(API), "combined": COMBINED}
    assert refused[0].actor == f"capability:{COMBINED}" and refused[0].incident_id == "inc_combined"
    # the refused sub-read is stored and referenced like the others, as the combined capability's caller
    assert len(obs.values["subcalls"]) == 3
    stored = {r.evidence_id: r for r in mem}
    last = stored[obs.values["subcalls"][-1]]
    assert (last.status, last.caller, last.capability) == ("refused", f"capability:{COMBINED}", "container.status")
    assert last.values["error_category"] == "forbidden" and str(last.target) == str(API)



def test_a_refused_sub_read_keeps_its_own_target_and_reason_not_the_incidents():
    spec = _fake_combined([("host.memory", HOST, {})] * 3)                     # the third is past max_subcalls
    obs, ref, audit, mem, _ = _run(spec)
    last = {r.evidence_id: r for r in mem}[obs.values["subcalls"][-1]]
    assert last.status == "refused" and str(last.target) == str(HOST)          # not the incident's target (API)
    assert last.model_text == f"REFUSED host.memory: {COMBINED} may read 2 times"


def test_a_nested_combined_call_is_recorded_with_its_target_and_reason():
    spec = _fake_combined([("analysis.diagnostic_snapshot", HOST, {})])
    obs, ref, audit, mem, _ = _run(spec)
    last = {r.evidence_id: r for r in mem}[obs.values["subcalls"][-1]]
    assert str(last.target) == str(HOST)
    assert last.model_text == "REFUSED analysis.diagnostic_snapshot: a combined capability cannot call another one"
    nested = [a for a in audit if a.policy_rule == "nested_combined"]
    assert nested[0].detail == {"reason": "a combined capability cannot call another one", "target": str(HOST),
                                "combined": COMBINED}

def test_a_sub_read_passes_its_arguments_and_target_through_the_entry_point():
    class Recording(Catalogue):
        def call(self, spec, args, target):
            self.args = args.model_dump()
            return super().call(spec, args, target)

    spec = _fake_combined([("container.logs", API, {"tail": 37})])
    cat = Recording({COMBINED: spec})
    inv, ctx, _, _ = _invoke(cat)
    obs, _ = inv(ctx, COMBINED, {"target": str(API)})
    assert obs.values["statuses"] == ["ok"]
    assert cat.calls == [("container.logs", str(API))] and cat.args["tail"] == 37


def test_the_sub_read_values_list_ids_and_full_refs_in_the_same_order():
    spec = _fake_combined([("container.status", API, {}), ("container.resources", API, {})])
    obs, *_ = _run(spec)
    refs = obs.values["subcall_refs"]
    assert obs.values["subcalls"] == [r["evidence_id"] for r in refs]
    assert [r["capability"] for r in refs] == ["container.status", "container.resources"]
    assert all(r["sha256"] and r["kind"] == "observation" for r in refs)


# --- the inspection policy: an absolute deny pattern with a wildcard ---------------------------------------------------

def test_an_absolute_deny_pattern_with_a_wildcard_refuses_every_path_it_matches():
    p = InspectionPolicy.from_data({"targets": {"vm-166/host:vm-166": {"files": ["/var/log/myapp/"]}},
                                    "deny": ["/var/log/myapp/private-*"], "arbitrary_exec": False})
    host = TargetRef.parse("vm-166/host:vm-166")
    denied = p.allows(host, "host.read_file", {"path": "/var/log/myapp/private-2026.log"})
    assert not denied.allowed and "private-*" in denied.reason
    assert p.allows(host, "host.read_file", {"path": "/var/log/myapp/app.log"}).allowed
