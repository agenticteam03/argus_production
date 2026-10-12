"""E2E-5: a rule-planned confirmation round before the model concludes on a disk-pressure incident.

After E2E-3 the model sees which running container has the full filesystem mounted read-write, but in 2 of 5 SC-05
runs it called that container "the likely writer" and still named the host, because it had not read its logs. The
`confirm_then_reason` strategy (§10.3: a strategy only returns decisions) plans one round of the suspect's logs and
resources by rule the first time a suspect appears in the evidence, then lets the model loop decide as before.
"""
from __future__ import annotations

from argus.domain.model import (Escalate, EvidenceRef, Incident, IncidentStatus, ReadCall, RequestKind, TargetRef,
                                TriggerKind, UseReadTools, utcnow)
from argus.orchestration.strategies import ConfirmThenReasonStrategy
from argus.orchestration.view import InvestigationView
from test_core import make_app  # noqa: F401  (make_app is a fixture)

HOST = TargetRef.parse("vm-166/host:vm-166")
FILLER = "vm-166/container:argus-lab-filler"
API = "vm-166/container:argus-lab-api"
FILL = "/srv/argus-lab-fill"


class Harness:
    """Stands in for the model: records that it was asked and returns a marker decision."""

    def __init__(self):
        self.asked = 0

    def decide(self, view):
        self.asked += 1
        return Escalate(reason="model decided", evidence_ids=[])


def _ev(n: int, capability: str, text: str, status: str = "ok") -> EvidenceRef:
    return EvidenceRef(evidence_id=f"ev{n}", sha256="0" * 64, capability=capability, status=status, model_text=text)


def _disk(fill_pct: float) -> EvidenceRef:
    return _ev(1, "host.disk_usage", f"vm-166:/ used=28.0% free=35611 MiB inodes_used=2.8%; "
                                     f"vm-166:{FILL} used={fill_pct}% free=17 MiB inodes_used=0.1%")


def _status(n: int, target: str, state: str = "running", mounts: str = f"{FILL}(rw)") -> EvidenceRef:
    tail = f" host_mounts={mounts} other_binds=1" if mounts else ""
    return _ev(n, "container.status", f"{target}: state={state} health=none restarts=0 networks=none{tail}")


def _view(evidence, decisions=()) -> InvestigationView:
    inc = Incident(id="inc_e2e5", target=HOST, trigger_kind=TriggerKind.manual, request_kind=RequestKind.report,
                   reason="the disk is almost full", principal="test", trigger_id="test:e2e5",
                   status=IncidentStatus.running,
                   opened_at=utcnow())
    return InvestigationView(incident=inc, incident_class=None, findings=[], passages=[], evidence=list(evidence),
                             decisions_so_far=list(decisions), offered_specs=[], scope=[], steps_left=5,
                             max_reads_per_step=4)


def _read(name: str, target: str) -> ReadCall:
    return ReadCall(name=name, arguments={"target": target})


def test_a_running_rw_writer_of_the_full_filesystem_gets_its_logs_and_resources_read_first():
    harness = Harness()
    s = ConfirmThenReasonStrategy(harness)
    d = s.next_step(_view([_disk(92.6), _status(2, FILLER), _status(3, API, mounts="")]))
    assert isinstance(d, UseReadTools) and s.last_source == "rule" and harness.asked == 0
    assert [(c.name, c.arguments["target"]) for c in d.calls] == [("container.logs", FILLER),
                                                                  ("container.resources", FILLER)]


def test_the_round_is_planned_once_then_the_model_decides():
    harness = Harness()
    s = ConfirmThenReasonStrategy(harness)
    done = UseReadTools(calls=[_read("container.logs", FILLER), _read("container.resources", FILLER)])
    d = s.next_step(_view([_disk(92.6), _status(2, FILLER)], decisions=[done]))
    assert harness.asked == 1 and s.last_source == "model" and d.reason == "model decided"


def test_no_suspect_means_the_model_loop_as_before():
    # a stopped writer IS a suspect since EVAL-2 (ACR-0008): tests/test_eval2_fixes.py
    for evidence in ([_disk(92.6)],                                         # no container status read yet
                     [_disk(92.6), _status(2, FILLER, mounts=f"{FILL}(ro)")],     # read-only: not a writer
                     [_disk(41.0), _status(2, FILLER)],                             # the mount is not the full one
                     [_disk(92.6), _status(2, FILLER, mounts="")]):                 # no declared mount at all
        harness = Harness()
        s = ConfirmThenReasonStrategy(harness)
        s.next_step(_view(evidence))
        assert harness.asked == 1 and s.last_source == "model", evidence


def test_two_writers_are_both_read_in_one_round():
    s = ConfirmThenReasonStrategy(Harness())
    other = "vm-166/container:argus-lab-filler-2"
    d = s.next_step(_view([_disk(95.0), _status(2, FILLER), _status(3, other)]))
    assert sorted({c.arguments["target"] for c in d.calls}) == sorted([FILLER, other])


def test_without_a_model_it_escalates_like_model_loop():
    s = ConfirmThenReasonStrategy(None)
    d = s.next_step(_view([_disk(92.6)]))
    assert isinstance(d, Escalate) and s.last_source == "rule"


def test_disk_pressure_uses_the_new_strategy_and_the_wiring_knows_it():
    from argus.detectors.classes import CLASSES
    assert next(c for c in CLASSES if c.name == "disk_pressure").strategy == "confirm_then_reason"
    src = (__import__("pathlib").Path(__file__).resolve().parents[1] / "argus/infrastructure/wiring.py").read_text(
        encoding="utf-8")
    assert '"confirm_then_reason": ConfirmThenReasonStrategy(harness)' in src


# --- end to end through the real skeleton (the graph runs the rule-planned round between two model steps) -----------
def test_the_skeleton_reads_the_writer_before_the_model_concludes(make_app, monkeypatch):
    from argus.adapters.outbound.llm import ScriptedLLM
    from argus.domain.model import IncidentOutcome
    from test_core import FakeMetrics, FakeTargetAgent, incident

    vm166 = "http://argus-v18-tunnel:18701"                                 # vm-166's read path (the tunnel)
    gateway = dict(FakeTargetAgent.data[vm166])
    gateway.update({
        "/containers/argus-lab-filler/status": {"id": "fff666", "state": "running", "health": "none", "restart_count": 0,
                                                "networks": [], "host_mounts": [{"mount": FILL, "rw": True}],
                                                "other_binds": 1},
        "/containers/argus-lab-filler/logs": {"lines": ["filler: wrote 202 MiB to /fill, 92.6% used"]},
        "/containers/argus-lab-filler/stats": {"memory_usage_bytes": 6500000, "memory_limit_bytes": 50331648}})
    monkeypatch.setitem(FakeTargetAgent.data, vm166, gateway)
    real_get = FakeTargetAgent.get

    def get(self, path, params=None):
        if self.kind == "host_probe" and path == "/disk":
            used = {"/": 28.0, FILL: 92.6}[params["mount"]]
            return {"mount": params["mount"], "used_percent": used, "free_mib": 17, "inodes_used_percent": 1.0}
        return real_get(self, path, params)
    monkeypatch.setattr(FakeTargetAgent, "get", get)

    asked = []

    def script(ctx: str):
        asked.append(ctx)
        if "inodes_used" not in ctx:                                          # 1: the disk
            return {"calls": [("get_disk_usage", {"target": str(HOST)})]}
        if "host_mounts" not in ctx:                                          # 2: the suspect's status
            return {"calls": [("get_container_status", {"target": FILLER})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "argus-lab-filler writes /srv/argus-lab-fill (its logs: 202 MiB)",
                                        "evidence_ids": ids[-1:], "confidence": "high",
                                        "root_cause_target": FILLER})]}

    app = make_app(llm=ScriptedLLM(script),
                   metrics=FakeMetrics({str(HOST): {"host_disk_used_ratio_5m": 0.926, "host_disk_hours_to_full": 0.3}}))
    inc = app.runner.run(incident(app, str(HOST), reason="the disk is almost full").id)
    caps = [e.capability for e in app.store.list_evidence(inc.id)]
    assert inc.outcome == IncidentOutcome.diagnosed and inc.root_cause_target == FILLER
    assert caps.index("container.status") < caps.index("container.logs") and "container.resources" in caps
    assert len(asked) == 3 and "wrote 202 MiB" in asked[-1]       # the model concluded with the filler's logs in view
