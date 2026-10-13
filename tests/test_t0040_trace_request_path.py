"""T-0040: `trace_request_path` (`analysis.trace_request_path`, ARCHITECTURE §12 Level 3, combined §12.7): follows the
inventory's dependency graph from a container. For each declared dependency on the same host (at most 3): is it
running (`container.status`), do the two share a Docker network (`network.connectivity`), does its name resolve from
the app network (`network.resolve_dns`). Every sub-read goes through `InvokeCapability` (policy, budget, audit,
evidence) like the snapshot's; a dependency on another host or a host target is listed, never read across hosts.
Offered to no class until measured. TCP to the dependency's port is not in it: a combined impl knows only the
investigated target's inventory entry, not its dependencies' ports.
"""
from __future__ import annotations

import uuid

import yaml

from argus.application.invoke_capability import InvocationContext, InvokeCapability
from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES
from argus.domain.model import Incident, Observation, TargetInfo, TargetRef, utcnow
from argus.policy.engine import PolicyEngine

SPECS = {s.name: s for s in build_catalog()}
S = SPECS["analysis.trace_request_path"]
API = TargetRef.parse("vm-166/container:argus-lab-api")
CACHE = TargetRef.parse("vm-166/container:argus-lab-cache")
HOST = TargetRef.parse("vm-166/host:vm-166")
OTHER = TargetRef.parse("vm-095/container:argus-lab-api")
SUBS = ["container.status", "network.connectivity", "network.resolve_dns"]


class Catalogue:
    def __init__(self, answers=None):
        self.calls, self.answers = [], answers or {}

    def spec(self, name):
        return SPECS.get(name)

    def call(self, spec, args, target):
        self.calls.append((spec.name, str(target)))
        status, text = self.answers.get((spec.name, str(target)), ("ok", f"{spec.name} of {target}: fine"))
        return Observation(observation_id=f"obs_{uuid.uuid4().hex[:16]}", status=status, capability=spec.name,
                           target=target, host=target.host, executor=spec.executor, collected_at=utcnow(),
                           model_text=text)


class Inventory:
    def __init__(self, deps):
        self.deps = deps

    def target(self, ref):
        return TargetInfo(ref=ref, depends_on=self.deps) if ref == API else TargetInfo(ref=ref)


class Redactor:
    def value(self, v):
        return v, 0

    def text(self, t):
        return t, 0


class Memory(list):
    def append_evidence(self, rec):
        self.append(rec)


def _invoke(catalogue, deps, scope=(API, CACHE, HOST)):
    caps = {n: {"max_per_incident": 6} for n in SUBS}
    caps["analysis.trace_request_path"] = {"max_per_incident": 1}
    data = {"profile": "production", "max_tool_level": 3, "capabilities": caps}
    audit, mem = [], Memory()
    sink = type("A", (), {"append": lambda self, r: audit.append(r)})()
    inv = InvokeCapability(catalogue, PolicyEngine(data, yaml.safe_dump(data)), Inventory(deps), mem, sink, Redactor())
    ctx = InvocationContext(incident=Incident.model_construct(id="inc_trace", target=API), caller="model",
                            scope=set(scope))
    return inv, ctx, audit, mem


def test_a_level_3_combined_capability_in_the_worker_offered_to_no_class():
    assert (S.model_name, S.level, S.executor, S.runs_in, S.max_subcalls) == (
        "trace_request_path", 3, "argus_internal", "worker", 9)
    assert S.target_kinds == frozenset({"container"})
    assert [c.name for c in CLASSES if S.tags & c.tool_tags] == []
    pol = yaml.safe_load(open("config/policy.yaml", encoding="utf-8"))
    assert pol["capabilities"]["analysis.trace_request_path"]["max_per_incident"] == 1


def test_each_dependency_hop_is_read_through_invoke_capability():
    cat = Catalogue()
    inv, ctx, audit, mem = _invoke(cat, [CACHE])
    obs, ref = inv(ctx, "analysis.trace_request_path", {"target": str(API)})
    assert obs.status == "ok" and ref is not None
    assert cat.calls == [("container.status", str(CACHE)), ("network.connectivity", str(API)),
                         ("network.resolve_dns", str(CACHE))]
    subs = [r for r in mem if r.capability in SUBS]
    assert len(subs) == 3 and all(r.caller == "capability:analysis.trace_request_path" for r in subs)
    assert all(r.evidence_id in obs.model_text for r in subs)
    assert "argus-lab-api -> argus-lab-cache" in obs.model_text


def test_a_hop_that_fails_is_said_and_the_trace_goes_on():
    cat = Catalogue({("container.status", str(CACHE)): ("error", "container.status of cache: exited (137)")})
    inv, ctx, _, _ = _invoke(cat, [CACHE])
    obs, _ = inv(ctx, "analysis.trace_request_path", {"target": str(API)})
    assert obs.partial and "not ok: container.status" in obs.model_text and len(cat.calls) == 3


def test_no_declared_dependency_is_said_plainly():
    cat = Catalogue()
    inv, ctx, _, _ = _invoke(cat, [])
    obs, _ = inv(ctx, "analysis.trace_request_path", {"target": str(API)})
    assert cat.calls == [] and "no declared dependency" in obs.model_text


def test_a_host_dependency_or_another_hosts_container_is_listed_never_read():
    cat = Catalogue()
    inv, ctx, _, _ = _invoke(cat, [HOST, OTHER, CACHE])
    obs, _ = inv(ctx, "analysis.trace_request_path", {"target": str(API)})
    assert {t for _, t in cat.calls} <= {str(API), str(CACHE)}
    assert "vm-166/host:vm-166: not traced" in obs.model_text and "vm-095/container:argus-lab-api: not traced" in obs.model_text


def test_at_most_three_dependencies_are_traced():
    deps = [TargetRef.parse(f"vm-166/container:argus-lab-d{i}") for i in range(5)]
    cat = Catalogue()
    inv, ctx, _, _ = _invoke(cat, deps, scope=(API, *deps))
    obs, _ = inv(ctx, "analysis.trace_request_path", {"target": str(API)})
    assert len(cat.calls) == 9 and "2 more not traced" in obs.model_text
