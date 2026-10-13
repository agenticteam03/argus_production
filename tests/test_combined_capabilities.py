"""ARCHITECTURE §12.7: combined capabilities gather several reads into one result, every sub-read through
`InvokeCapability` (validated, budgeted, policy-checked, audited, stored), never an executor directly.

First use: `analysis.diagnostic_snapshot` (Level 3, in the worker) — a container's status, resources and recent logs,
and its host's memory and CPU, in one call (`max_subcalls` 6). The combined result is stored as evidence too and
references its sub-observations by `evidence_id`. A sub-read past `max_subcalls`, a combined capability inside
another, or a target outside the incident's scope is refused and audited like any refused read.
"""
from __future__ import annotations

import uuid

import yaml

from argus.application.invoke_capability import InvocationContext, InvokeCapability
from argus.capabilities.catalog import build_catalog
from argus.capabilities.spec import CapabilityResult
from argus.detectors.classes import CLASSES
from argus.domain.model import Incident, Observation, TargetRef, utcnow
from argus.policy.engine import PolicyEngine

SPECS = {s.name: s for s in build_catalog()}
API = TargetRef.parse("vm-166/container:argus-lab-api")
HOST = TargetRef.parse("vm-166/host:vm-166")
OTHER = TargetRef.parse("vm-095/container:argus-lab-api")
SUBS = ["container.status", "container.resources", "container.logs", "host.memory", "host.cpu"]


class Catalogue:
    def __init__(self, extra=None):
        self.calls = []
        self.specs = {**SPECS, **(extra or {})}

    def spec(self, name):
        return self.specs.get(name)

    def call(self, spec, args, target):
        self.calls.append((spec.name, str(target)))
        return Observation(observation_id=f"obs_{uuid.uuid4().hex[:16]}", status="ok", capability=spec.name,
                           target=target, host=target.host, executor=spec.executor, collected_at=utcnow(),
                           model_text=f"{spec.name} of {target}: fine")


class Inventory:
    def target(self, ref):
        return object()


class Redactor:
    def value(self, v):
        return v, 0

    def text(self, t):
        return t, 0


class Memory(list):
    def append_evidence(self, rec):
        self.append(rec)


def _engine():
    caps = {n: {"max_per_incident": 4} for n in SUBS}
    caps["analysis.diagnostic_snapshot"] = {"max_per_incident": 1}
    caps["analysis.fake_combined"] = {"max_per_incident": 2}
    data = {"profile": "production", "max_tool_level": 3, "capabilities": caps}
    return PolicyEngine(data, yaml.safe_dump(data))


def _invoke(catalogue, scope=(API, HOST)):
    audit, mem = [], Memory()
    sink = type("A", (), {"append": lambda self, r: audit.append(r)})()
    inv = InvokeCapability(catalogue, _engine(), Inventory(), mem, sink, Redactor())
    ctx = InvocationContext(incident=Incident.model_construct(id="inc_combined", target=API), caller="model",
                            scope=set(scope))
    return inv, ctx, audit, mem


def test_the_snapshot_is_a_level_3_combined_capability_in_the_worker():
    s = SPECS["analysis.diagnostic_snapshot"]
    assert (s.model_name, s.level, s.executor, s.runs_in, s.max_subcalls) == \
           ("capture_diagnostic_snapshot", 3, "argus_internal", "worker", 6)
    assert s.target_kinds == frozenset({"container"})
    assert [c.name for c in CLASSES if s.tags & c.tool_tags] == ["health_check_failed"]   # EVAL-snapshot: measured
    pol = yaml.safe_load(open("config/policy.yaml", encoding="utf-8"))
    assert pol["capabilities"]["analysis.diagnostic_snapshot"]["max_per_incident"] == 1


def test_every_sub_read_goes_through_invoke_capability_and_is_referenced():
    cat = Catalogue()
    inv, ctx, audit, mem = _invoke(cat)
    obs, ref = inv(ctx, "analysis.diagnostic_snapshot", {"target": str(API)})
    assert obs.status == "ok" and ref is not None
    assert cat.calls == [("container.status", str(API)), ("container.resources", str(API)),
                         ("container.logs", str(API)), ("host.memory", str(HOST)), ("host.cpu", str(HOST))]
    subs = [r for r in mem if r.capability in SUBS]
    assert len(subs) == 5 and all(r.caller == "capability:analysis.diagnostic_snapshot" for r in subs)
    combined = next(r for r in mem if r.capability == "analysis.diagnostic_snapshot")
    assert combined.values["values"]["subcalls"] == [r.evidence_id for r in subs]
    assert all(r.evidence_id in obs.model_text for r in subs)
    requested = [a for a in audit if a.event == "tool.requested"]
    assert [a.actor for a in requested] == ["model"] + ["capability:analysis.diagnostic_snapshot"] * 5
    assert ctx.counters["container.status"] == 1 and ctx.counters["analysis.diagnostic_snapshot"] == 1


def _fake_combined(reads):
    """A combined capability whose impl asks the given reads (to test the guards)."""
    base = SPECS["analysis.diagnostic_snapshot"]

    def impl(args, target, info, invoker):
        got = [invoker.read(name, t, a) for name, t, a in reads]
        return CapabilityResult(values={"statuses": [o.status for o, _ in got]},
                                model_text="; ".join(f"{o.capability}={o.status}" for o, _ in got))
    from dataclasses import replace
    return replace(base, name="analysis.fake_combined", model_name="fake_combined", max_subcalls=2, impl=impl)


def test_sub_reads_past_max_subcalls_are_refused_and_audited():
    spec = _fake_combined([("container.status", API, {})] * 3)
    cat = Catalogue({"analysis.fake_combined": spec})
    inv, ctx, audit, _ = _invoke(cat)
    obs, _ = inv(ctx, "analysis.fake_combined", {"target": str(API)})
    assert obs.values["statuses"] == ["ok", "ok", "refused"] and len(cat.calls) == 2
    assert any(a.event == "tool.refused" and a.policy_rule == "max_subcalls" for a in audit)


def test_a_combined_capability_cannot_call_another_one():
    spec = _fake_combined([("analysis.diagnostic_snapshot", API, {})])
    cat = Catalogue({"analysis.fake_combined": spec})
    inv, ctx, audit, _ = _invoke(cat)
    obs, _ = inv(ctx, "analysis.fake_combined", {"target": str(API)})
    assert obs.values["statuses"] == ["refused"] and cat.calls == []
    assert any(a.event == "tool.refused" and a.policy_rule == "nested_combined" for a in audit)


def test_a_sub_read_outside_the_incident_scope_is_refused_by_the_policy():
    spec = _fake_combined([("container.status", OTHER, {}), ("container.status", API, {})])
    cat = Catalogue({"analysis.fake_combined": spec})
    inv, ctx, audit, _ = _invoke(cat)
    obs, _ = inv(ctx, "analysis.fake_combined", {"target": str(API)})
    assert obs.values["statuses"] == ["refused", "ok"] and cat.calls == [("container.status", str(API))]
    assert any(a.event == "tool.refused" and a.policy_rule == "incident_scope" for a in audit)


def test_the_incident_budget_is_shared_with_sub_reads():
    spec = _fake_combined([("container.status", API, {}), ("container.status", API, {})])
    cat = Catalogue({"analysis.fake_combined": spec})
    inv, ctx, audit, _ = _invoke(cat)
    ctx.counters["container.status"] = 3                                     # one left of 4
    obs, _ = inv(ctx, "analysis.fake_combined", {"target": str(API)})
    assert obs.values["statuses"] == ["ok", "refused"]
    assert any(a.policy_rule == "max_per_incident" for a in audit)


def test_the_combined_impl_gets_no_executor():
    seen = {}
    base = _fake_combined([])

    def impl(args, target, info, invoker):
        seen["attrs"] = {a for a in dir(invoker) if not a.startswith("_")}
        return CapabilityResult(values={}, model_text="x")
    from dataclasses import replace
    spec = replace(base, impl=impl)
    inv, ctx, _, _ = _invoke(Catalogue({"analysis.fake_combined": spec}))
    inv(ctx, "analysis.fake_combined", {"target": str(API)})
    assert seen["attrs"] == {"read"}


def test_the_runners_get_the_sub_reads_as_evidence_the_model_can_cite():
    """Both runners append `refs_of(obs, ref)`: the sub-reads first, then the combined result (OP-012 counts them)."""
    from argus.application.invoke_capability import refs_of
    cat = Catalogue()
    inv, ctx, _, mem = _invoke(cat)
    obs, ref = inv(ctx, "analysis.diagnostic_snapshot", {"target": str(API)})
    refs = refs_of(obs, ref)
    assert [r.capability for r in refs] == SUBS + ["analysis.diagnostic_snapshot"]
    assert refs[-1] == ref and all(r.evidence_id in {m.evidence_id for m in mem} for r in refs)
    plain = Catalogue()
    inv2, ctx2, _, _ = _invoke(plain)
    o2, r2 = inv2(ctx2, "container.status", {"target": str(API)})
    assert refs_of(o2, r2) == [r2] and refs_of(o2, None) == []
