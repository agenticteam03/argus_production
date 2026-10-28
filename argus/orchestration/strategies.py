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
_LINK_LINE = re.compile(r"(?m)^- (?P<owner>[^ ]+) -> (?P<dependency>[^:]+): (?P<state>ok|slow|broken|unknown)\b")


def _fields(text: str) -> dict[str, str]:
    """`key=value` pairs of an Argus capability text (the format is Argus's own, see capabilities/catalog.py)."""
    return {k: v.strip(",") for k, v in _KV.findall(text or "")}


def _about(text: str) -> str | None:
    """The target a container capability text is about: it starts with `<host>/<kind>:<name>: `."""
    head = (text or "").split(": ", 1)[0]
    return head if "/" in head and ":" in head else None


# --- E2E-5 (ACR-0007): a rule-planned confirmation round, then the model loop ---------------------------------------
DISK_FULL_PCT = 90.0                     # disk_pressure's detector threshold (classes.py: used >= 0.9)
_DISK = re.compile(r"\S+?:(/[^\s;]*) used=([0-9.]+)%")
_MOUNT = re.compile(r"([^\s,]+)\((rw|ro)\)")


def disk_suspects(view: InvestigationView, include_stopped: bool = False) -> list[str]:
    """The running containers that have a full declared filesystem mounted read-write, from evidence already read:
    `host.disk_usage` (the mounts at or above the detector's threshold) and `container.status` (`host_mounts`,
    E2E-3). In evidence order, each once. `include_stopped`: an exited writer too, whose data stays on the mount
    (EVAL-2, ACR-0008); the baseline's rule keeps running writers only."""
    states = {"running", "exited"} if include_stopped else {"running"}
    ok = [e for e in view.evidence if e.status == "ok"]
    full = {m for e in ok if e.capability == "host.disk_usage"
            for m, pct in _DISK.findall(e.model_text or "") if float(pct) >= DISK_FULL_PCT}
    out: list[str] = []
    for e in ok:
        if e.capability != "container.status":
            continue
        f, who = _fields(e.model_text), _about(e.model_text)
        if who and f.get("state") in states and who not in out and any(
                mode == "rw" and m in full for m, mode in _MOUNT.findall(f.get("host_mounts", ""))):
            out.append(who)
    return out


class ConfirmThenReasonStrategy:
    """The model loop, with one rule-planned round when a suspect appears: the logs and resources of each running
    container that writes the full filesystem (E2E-5). The model then decides with that proof in front of it; the
    round is planned once per suspect. Deterministic given the evidence (§10.3)."""
    name = "confirm_then_reason"

    def __init__(self, harness: Any | None):
        self.loop = ModelLoopStrategy(harness)
        self.last_source = "rule"

    def next_step(self, view: InvestigationView):
        planned = {c.arguments.get("target") for d in view.decisions_so_far if isinstance(d, UseReadTools)
                   for c in d.calls if c.name == "container.logs"}
        running = set(disk_suspects(view))
        pending = [s for s in disk_suspects(view, include_stopped=True) if s not in planned]
        if pending and self.loop.harness is not None:
            self.last_source = "rule"
            return UseReadTools(calls=[ReadCall(name=n, arguments={"target": s}) for s in pending
                                       for n in (("container.logs", "container.resources") if s in running
                                                 else ("container.logs",))])     # a stopped one has no resources
        d = self.loop.next_step(view)
        self.last_source = self.loop.last_source
        return d


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
            peers = [x for x in view.scope if x.kind == "container" and x != t]
            return [ReadCall(name="container.health", arguments={"target": ts}),
                    *[ReadCall(name="container.status", arguments={"target": str(x)}) for x in [t, *peers]],
                    *self._link_state_read(view)]
        if cls == "dependency_unavailable":
            others = [x for x in view.scope if x.kind == "container" and x != t]
            calls = [ReadCall(name="container.status", arguments={"target": str(x)}) for x in [t, *others]]
            return [*calls, *self._link_state_read(view)]
        if cls == "postgresql_connection_exhaustion":
            return [ReadCall(name="database.health", arguments={"target": ts})]
        if cls == "nginx_upstream_failure":
            others = [x for x in view.scope if x.kind == "container" and x != t]
            calls = [ReadCall(name="container.status", arguments={"target": str(x)}) for x in [t, *others]]
            return [*calls, *self._link_state_read(view)]
        if cls == "worker_stalled":
            others = sorted((x for x in view.scope if x.kind == "container" and x != t), key=str)
            calls = [ReadCall(name="container.status", arguments={"target": str(x)}) for x in [t, *others]]
            return [*calls, *self._link_state_read(view)]
        if cls == "cpu_saturation":
            return [ReadCall(name="container.status", arguments={"target": ts}),
                    ReadCall(name="container.resources", arguments={"target": ts})]
        if cls == "disk_pressure":       # EVAL-1: every declared mount, and the containers in the host's scope
            others = [x for x in view.scope if x.kind == "container"]
            return [ReadCall(name="host.disk_usage", arguments={"target": ts}),
                    *[ReadCall(name="container.status", arguments={"target": str(x)}) for x in others]]
        return evidence_pack_plan(t)

    def next_step(self, view: InvestigationView):
        if not any(isinstance(d, UseReadTools) for d in view.decisions_so_far):
            return UseReadTools(calls=self.plan(view))
        confirm = self._confirm(view)
        if confirm:
            return UseReadTools(calls=confirm)
        ok = [e for e in view.evidence if e.status == "ok"]
        rules = {"container_restart_loop": self._restart, "health_check_failed": self._health,
                 "dependency_unavailable": self._dependency, "postgresql_connection_exhaustion": self._database,
                 "nginx_upstream_failure": self._gateway, "worker_stalled": self._worker_stalled,
                 "cpu_saturation": self._cpu, "disk_pressure": self._disk}
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

    @staticmethod
    def _link_state_read(view) -> list[ReadCall]:
        """The deterministic dependency/gateway baselines must explicitly consume offered Level 2 evidence."""
        if any(spec.name == "network.link_states" for spec in view.offered_specs):
            return [ReadCall(name="read_link_states", arguments={"target": str(view.incident.target), "minutes": 30})]
        return []

    @staticmethod
    def _link_state(view, owner: TargetRef, dependency: TargetRef) -> tuple[str, str] | None:
        """Read one link state from the bounded text produced by Argus's own `network.link_states` capability."""
        for evidence in view.evidence:
            if evidence.status != "ok" or evidence.capability != "network.link_states":
                continue
            for match in _LINK_LINE.finditer(evidence.model_text):
                if match.group("owner") == owner.name and match.group("dependency") == dependency.name:
                    return match.group("state"), match.group(0).lstrip("- ")
        return None

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
            return None                  # SIGKILL without an OOM kill: nothing says who sent it (RB-008, EVAL-3)
        if code not in ("0", "unknown", "None"):
            return (f"non-OOM application crash: the process exits with code {code} on every start; restarting does "
                    f"not fix it (see its logs)", t)
        return None

    def _health(self, view, ok):
        t = str(view.incident.target)
        h = self._texts(ok, "container.health").get(t)
        if not h or h.get("health") != "unhealthy":
            return None
        for dep in sorted((x for x in view.scope if x.kind == "container" and str(x) != t), key=str):
            link = self._link_state(view, view.incident.target, dep)
            if link and link[0] == "broken":
                return (f"its health check is failing while the recorded link from {t} to {dep} is broken ({link[1]}): "
                        f"the dependency path is the cause to investigate", str(dep))
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
        for dep in sorted((x for x in view.scope if x.kind == "container" and str(x) != t), key=str):
            link = self._link_state(view, view.incident.target, dep)
            if link and link[0] == "broken":
                return (f"the recorded probe shows the declared link from {t} to {dep} is broken ({link[1]}): "
                        f"the failure is reachability to the dependency, not proof that {dep} is stopped", str(dep))
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
        upstream = next((x for x in view.scope if str(x) == up), None)
        link = self._link_state(view, view.incident.target, upstream) if upstream else None
        if link and link[0] == "broken":
            return (f"the proxy {t} answers 502/504 and its recorded link to upstream {up} is broken ({link[1]}): "
                    f"the root cause is loss of reachability to {up}, not a proxy failure", up)
        if link and link[0] == "slow":
            return (f"the proxy {t} answers 502/504 and its recorded link to upstream {up} is slow ({link[1]}): "
                    f"the upstream path is slow, so restarting the proxy would not help", up)
        return (f"the proxy {t} answers 502/504 while its upstream {up} is running: {up} does not answer within the "
                f"proxy's timeout (slow or saturated upstream, RB-015 H3); the root cause is {up}, not the proxy", up)

    def _worker_stalled(self, view, ok):
        """RB-022: a dependency whose status or recorded link is direct evidence is the cause; a running worker whose
        declared dependencies were all read as running, with no broken link, is itself the cause (alive, not consuming).
        A dependency that was not read is unknown, never healthy."""
        target = view.incident.target
        t = str(target)
        status = self._texts(ok, "container.status")
        worker = status.get(t)
        if not worker or worker.get("state") != "running":
            return None                         # a contradictory/stopped worker needs a different incident path
        dependencies = sorted((x for x in view.scope if x.kind == "container" and x != target), key=str)
        for dependency in dependencies:
            ref = str(dependency)
            dep_status = status.get(ref)
            if dep_status and dep_status.get("state") not in ("running", None):
                return (f"the stalled worker's dependency {ref} is {dep_status['state']}; investigate that dependency "
                        "before restarting the worker", ref)
            link = self._link_state(view, target, dependency)
            if link and link[0] == "broken":
                return (f"the recorded worker dependency link to {ref} is broken ({link[1]}); investigate the "
                        "dependency path before restarting the worker", ref)
        if any((status.get(str(dependency)) or {}).get("state") != "running" for dependency in dependencies):
            return None                         # a dependency that was not read is unknown, not healthy
        return (f"{t} is running and its declared dependencies are running with no broken link, yet it is not consuming "
                "its queue (RB-022): the worker loop is the cause; a restart needs preserved evidence and a human "
                "approval", t)

    @staticmethod
    def _confirm(view) -> list[ReadCall]:
        """disk_pressure's second round: the logs of the one candidate writer, once. A rw mount shows access, not who
        wrote the data, so the rule below needs that read too."""
        if not view.incident_class or view.incident_class.name != "disk_pressure":
            return []
        found = disk_suspects(view)
        planned = {c.arguments.get("target") for d in view.decisions_so_far if isinstance(d, UseReadTools)
                   for c in d.calls if c.name == "container.logs"}
        return [ReadCall(name="container.logs", arguments={"target": found[0]})] if (
            len(found) == 1 and found[0] not in planned) else []

    def _disk(self, view, ok):
        """RB-005 (EVAL-1): exactly one running container writes (rw) a declared filesystem at or above the detector's
        threshold, and a read of its logs returned lines: it is the writer. A rw mount alone is access, not authorship;
        no logs, none or several candidates: the evidence does not say who, so escalate. The rule checks Argus's own
        line count, never the log text (the model reads that)."""
        found = disk_suspects(view)
        if len(found) != 1:
            return None
        who = found[0]
        text = (self._texts_raw(ok, "container.logs").get(who) or "").split(": ", 1)[-1]
        logs = re.match(r"last (\d+) log lines", text)
        if not logs or int(logs.group(1)) == 0:
            return None
        mounts = self._texts(ok, "container.status")[who].get("host_mounts", "")
        return (f"{who} writes a full declared filesystem of {view.incident.target.host} ({mounts}) and its logs were "
                f"read: the host's disk pressure comes from that writer (RB-005); freeing space without stopping it "
                f"would not last", who)

    @staticmethod
    def _texts_raw(ok, capability: str) -> dict[str, str]:
        return {_about(e.model_text): e.model_text for e in ok if e.capability == capability and _about(e.model_text)}

    def _cpu(self, view, ok):
        """RB-006 (T-0028): the container uses (nearly) all of its CPU quota: it is CPU-bound at its own limit."""
        t = str(view.incident.target)
        st = self._texts(ok, "container.status").get(t)
        res = next((e for e in ok if e.capability == "container.resources" and _about(e.model_text) == t), None)
        m = re.search(r"cpu=([0-9.]+)% of one CPU", res.model_text) if res else None
        try:
            limit = float(st.get("cpu_limit_cores", "")) if st else None
        except ValueError:
            limit = None
        if not m or not limit:
            return None                        # no quota or no usage read: unknown, escalate
        used = float(m.group(1))
        if used < 0.8 * limit * 100:
            return None                        # well under its quota: the throttling is not explained by the evidence
        return (f"CPU-bound at its own quota: it uses {used:g}% of one CPU against a limit of {limit:g} cores, so the "
                f"kernel throttles it; a busy or heavier workload than its limit allows (RB-006 H2/H5)", t)

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
