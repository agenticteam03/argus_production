"""Diagnostic strategies (v1.8 §10.3). A strategy only RETURNS decisions; it never executes anything.

Imports domain only; the model-tool harness is injected.
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from argus.domain.model import Conclude, Escalate, InvalidDecision, ReadCall, TargetRef, UseReadTools
from argus.orchestration.view import InvestigationView


class DiagnosticStrategy(Protocol):
    name: str
    def next_step(self, view: InvestigationView) -> Any: ...


def evidence_pack_plan(target: TargetRef) -> list[ReadCall]:
    """The fixed, model-free Level 1 evidence pack (v1.8 §10.7)."""
    host_t = f"{target.host}/host:{target.host}"
    calls: list[ReadCall] = []
    if target.kind == "container":
        t = str(target)
        calls += [ReadCall(name="container.status", arguments={"target": t}),
                  ReadCall(name="container.resources", arguments={"target": t}),
                  ReadCall(name="container.health", arguments={"target": t}),
                  ReadCall(name="container.logs", arguments={"target": t, "tail": 30})]
    calls += [ReadCall(name="host.memory", arguments={"target": host_t}),
              ReadCall(name="host.cpu", arguments={"target": host_t})]
    return calls


class EvidencePackStrategy:
    name = "evidence_pack"
    last_source = "rule"

    def next_step(self, view: InvestigationView):
        if not any(isinstance(d, UseReadTools) for d in view.decisions_so_far):
            return UseReadTools(calls=evidence_pack_plan(view.incident.target))
        return Escalate(reason="evidence pack collected; no diagnosis is claimed",
                        evidence_ids=sorted(view.evidence_ids))


class ModelLoopStrategy:
    name = "model_loop"

    def __init__(self, harness: Any | None):
        self.harness = harness
        self.last_source = "rule"          # "model" when the harness produced the decision

    def next_step(self, view: InvestigationView):
        if self.harness is None:
            self.last_source = "rule"
            return Escalate(reason="no model configured; escalating with deterministic evidence",
                            evidence_ids=sorted(view.evidence_ids))
        self.last_source = "model"
        return self.harness.decide(view)


class PlanThenReasonStrategy:
    """A fixed first round from the evidence pack, then the model loop."""
    name = "plan_then_reason"

    def __init__(self, harness: Any | None):
        self.loop = ModelLoopStrategy(harness)
        self.last_source = "rule"

    def next_step(self, view: InvestigationView):
        if not any(isinstance(d, UseReadTools) for d in view.decisions_so_far):
            self.last_source = "rule"
            return UseReadTools(calls=evidence_pack_plan(view.incident.target)[:3])
        d = self.loop.next_step(view)
        self.last_source = self.loop.last_source
        return d


def is_invalid(decision: Any) -> bool:
    return isinstance(decision, InvalidDecision)


# --- §21.2 "Baseline": the deterministic workflow every model strategy is measured against (T-0025) -----------------
_KV = re.compile(r"(\w+)=([^\s;]+)")


def _fields(text: str) -> dict[str, str]:
    """`key=value` pairs of an Argus capability text (the format is Argus's own, see capabilities/catalog.py)."""
    return {k: v.strip(",") for k, v in _KV.findall(text or "")}


def _about(text: str) -> str | None:
    """The target a container capability text is about: it starts with `<host>/<kind>:<name>: `."""
    head = (text or "").split(": ", 1)[0]
    return head if "/" in head and ":" in head else None


class BaselineStrategy:
    """Detector → top runbook → a fixed set of reads per class → a rule-based conclusion, or an escalation when no
    rule decides (never a guess). Deterministic: the same evidence gives the same decision. A failed read is never
    replaced by an assumption."""
    name = "baseline"
    last_source = "rule"

    def plan(self, view: InvestigationView) -> list[ReadCall]:
        cls = view.incident_class.name if view.incident_class else None
        t = view.incident.target
        ts = str(t)
        if cls == "container_restart_loop":
            return [ReadCall(name="container.status", arguments={"target": ts}),
                    ReadCall(name="container.logs", arguments={"target": ts, "tail": 30})]
        if cls == "health_check_failed":
            return [ReadCall(name="container.health", arguments={"target": ts}),
                    ReadCall(name="container.status", arguments={"target": ts})]
        if cls == "dependency_unavailable":
            others = [x for x in view.scope if x.kind == "container" and x != t]
            return [ReadCall(name="container.status", arguments={"target": str(x)}) for x in [t, *others]]
        if cls == "postgresql_connection_exhaustion":
            return [ReadCall(name="database.health", arguments={"target": ts})]
        if cls == "nginx_upstream_failure":
            others = [x for x in view.scope if x.kind == "container" and x != t]
            return [ReadCall(name="container.status", arguments={"target": str(x)}) for x in [t, *others]]
        return evidence_pack_plan(t)

    def next_step(self, view: InvestigationView):
        if not any(isinstance(d, UseReadTools) for d in view.decisions_so_far):
            return UseReadTools(calls=self.plan(view))
        ok = [e for e in view.evidence if e.status == "ok"]
        rules = {"container_restart_loop": self._restart, "health_check_failed": self._health,
                 "dependency_unavailable": self._dependency, "postgresql_connection_exhaustion": self._database,
                 "nginx_upstream_failure": self._gateway}
        rule = rules.get(view.incident_class.name if view.incident_class else "")
        found = rule(view, ok) if rule else None
        if found is None:
            return Escalate(reason="baseline: no rule decides from the evidence collected; escalating, not guessing",
                            evidence_ids=sorted(view.evidence_ids))
        diagnosis, root = found
        return Conclude(diagnosis=diagnosis, evidence_ids=sorted(e.evidence_id for e in ok), confidence="medium",
                        root_cause_target=root)

    @staticmethod
    def _texts(ok, capability: str) -> dict[str, dict[str, str]]:
        return {_about(e.model_text): _fields(e.model_text) for e in ok
                if e.capability == capability and _about(e.model_text)}

    def _restart(self, view, ok):
        t = str(view.incident.target)
        st = self._texts(ok, "container.status").get(t)
        if not st:
            return None
        code = st.get("exit_code", "unknown")
        if st.get("oom_killed") == "True":
            return (f"OOM-killed by its own container memory limit (oom_killed=True, exit {code}); it grows to the "
                    f"limit on every start, so a restart only helps until memory fills again", t)
        if code == "137":
            return ("killed by SIGKILL (exit 137) but not OOM (oom_killed=False): stopped from outside the "
                    "container, not by its memory limit", t)
        if code not in ("0", "unknown", "None"):
            return (f"non-OOM application crash: the process exits with code {code} on every start; restarting does "
                    f"not fix it (see its logs)", t)
        return None

    def _health(self, view, ok):
        t = str(view.incident.target)
        h = self._texts(ok, "container.health").get(t)
        if not h or h.get("health") != "unhealthy":
            return None
        streak = h.get("failing_streak", "unknown")
        return (f"its own health check is failing ({streak} consecutive failures) while the container keeps "
                f"running: the service inside is unhealthy", t)

    def _dependency(self, view, ok):
        t = str(view.incident.target)
        status = self._texts(ok, "container.status")
        mine = status.get(t)
        for dep, st in sorted(status.items()):
            if dep != t and st.get("state") not in ("running", None):
                return (f"its dependency {dep} is {st['state']}: {t} is a victim; the root cause is {dep}, "
                        f"and restarting {t} would not help", dep)
        for dep, st in sorted(status.items()):
            if dep == t or not mine or "networks" not in st or "networks" not in mine:
                continue
            a, b = set(mine["networks"].split(",")), set(st["networks"].split(","))
            if "unknown" not in a | b and not a & b:
                return (f"{dep} is running but shares no network with {t} ({dep} on {', '.join(sorted(b))}, {t} on "
                        f"{', '.join(sorted(a))}): a network misconfiguration, not a failed service; restarting "
                        f"either will not help", dep)
        return None

    def _gateway(self, view, ok):
        """RB-015 (T-0029): the proxy answers 502/504 (the detector); its one upstream in scope is the root cause, down
        or too slow. More than one candidate upstream: the evidence does not say which, so escalate."""
        t = str(view.incident.target)
        status = self._texts(ok, "container.status")
        if t not in status:
            return None
        ups = sorted(d for d in status if d != t)
        if len(ups) != 1:
            return None
        up, state = ups[0], status[ups[0]].get("state")
        if state not in ("running", None):
            return (f"the proxy {t} answers 502/504 because its upstream {up} is {state}: the root cause is {up}; "
                    f"restarting the proxy would not help (RB-015 H1)", up)
        return (f"the proxy {t} answers 502/504 while its upstream {up} is running: {up} does not answer within the "
                f"proxy's timeout (slow or saturated upstream, RB-015 H3); the root cause is {up}, not the proxy", up)

    def _database(self, view, ok):
        t = view.incident.target
        db = next((e for e in ok if e.capability == "database.health"), None)
        if db is None:
            return None
        m = re.search(r"top clients: ([^;]+)", db.model_text)
        first = m.group(1).split(",")[0].strip() if m else ""
        app, _, count = first.partition("=")
        app = app.split("/")[0]
        root = f"{t.host}/container:{app}"
        if not app or root not in {str(x) for x in view.scope}:
            return None
        return (f"connection slots almost exhausted by {app} ({count} connections, its oldest transaction left open): "
                f"the client {app} is the root cause, not the database; do not restart the database", root)
