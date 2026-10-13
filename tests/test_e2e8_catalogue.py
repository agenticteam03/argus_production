"""E2E-8 (phase 12): SC-10, SC-12 and the identity proof in the scenario runner's catalogue.

They need three things the runner did not have: a command or gate on another host than the scenario's (`on:` /
`host:`), and several investigations in one run (`investigations:`), all sent before the first is polled. Offline,
with the fake ssh and a fake API that answers per target.
"""
from __future__ import annotations

import re

import pytest

from test_e2e_runner import CATALOGUE, ME, Clock, FakeShell, e2e, incident


class MultiApi:
    """A fake API with one incident view per target; records the order of requests and polls."""

    def __init__(self, views: dict[str, dict]):
        self.views = views
        self.log: list[tuple[str, str]] = []

    def investigate(self, target: str, reason: str, kind: str) -> str:
        self.log.append(("investigate", target))
        return f"inc_{target}"

    def incident(self, iid: str) -> dict:
        target = iid.removeprefix("inc_")
        self.log.append(("poll", target))
        return {**self.views[target], "id": iid}


def healthy(target: str) -> dict:
    return incident(outcome="no_incident", incident_class=None, strategy=None, root_cause_target=None,
                    evidence=[{"target": target, "caller": "system", "capability": "container.status"}], audit=[])


def two_host_scenario(**kw):
    raw = {"id": "SC-T2", "title": "test", "host": "vm-166", "hosts": ["vm-166", "vm-095"],
           "start": ["sudo docker start a", {"host": "vm-095", "run": "sudo docker start b"}],
           "gate": [{"cmd": "echo ga", "expect": "^ok$"}, {"host": "vm-095", "cmd": "echo gb", "expect": "^ok$"}],
           "investigations": [
               {"request": {"target": "vm-166/container:argus-lab-worker", "reason": "r", "kind": "report"},
                "expect": {"outcome": "diagnosed", "first_runbook": "RB-001", "reads_on": "vm-166"}},
               {"request": {"target": "vm-095/container:argus-lab-api", "reason": "r", "kind": "check"},
                "expect": {"outcome": "no_incident", "model": "none", "reads_on": "vm-095"}}],
           "reset": [{"host": "vm-095", "run": "sudo docker rm -f b"}, "sudo docker rm -f a"]}
    raw.update(kw)
    return e2e.Scenario.from_dict(raw)


def views_ok() -> dict:
    return {"vm-166/container:argus-lab-worker": incident(),
            "vm-095/container:argus-lab-api": healthy("vm-095/container:argus-lab-api")}


def run(sc, shell, api, clock=None):
    clock = clock or Clock()
    return e2e.run_batch([sc], 1, shell, api, ME, now=clock.now, sleep=clock.sleep, log=lambda line: None)


# --- the runner -------------------------------------------------------------------------------------------------------
def test_commands_and_gates_run_on_the_host_they_name():
    shell = FakeShell({"echo ga": "ok", "echo gb": "ok"})
    [r] = run(two_host_scenario(), shell, MultiApi(views_ok()))
    assert r.verdict == "PASS", r.problems
    where = {cmd: host for host, cmd in shell.calls}
    assert where["sudo docker start a"] == "vm-166" and where["sudo docker start b"] == "vm-095"
    assert where["echo ga"] == "vm-166" and where["echo gb"] == "vm-095"
    assert where["sudo docker rm -f a"] == "vm-166" and where["sudo docker rm -f b"] == "vm-095"
    for h in ("vm-166", "vm-095"):         # the session marker and NO INTERFERENCE on every touched host
        assert (h, e2e.NONINT.format(label="after")) in shell.calls
        assert any(c.startswith("grep -q '^holder=") for host, c in shell.calls if host == h)


def test_every_investigation_is_sent_before_the_first_poll_and_each_is_graded():
    api = MultiApi(views_ok())
    [r] = run(two_host_scenario(), FakeShell({"echo ga": "ok", "echo gb": "ok"}), api)
    assert [k for k, _ in api.log[:2]] == ["investigate", "investigate"]      # together, not one after the other
    assert r.verdict == "PASS" and len(r.investigations) == 2
    assert {i["target"]: i["outcome"] for i in r.investigations} == {
        "vm-166/container:argus-lab-worker": "diagnosed", "vm-095/container:argus-lab-api": "no_incident"}


def test_one_wrong_investigation_fails_the_run_and_names_its_target():
    views = views_ok()
    views["vm-095/container:argus-lab-api"]["evidence"].append(
        {"target": "vm-166/container:argus-lab-api", "caller": "system", "capability": "container.status"})
    [r] = run(two_host_scenario(), FakeShell({"echo ga": "ok", "echo gb": "ok"}), MultiApi(views))
    assert r.verdict == "FAIL"
    assert r.problems == ["vm-095/container:argus-lab-api: read on another host: vm-166/container:argus-lab-api "
                          "(container.status)"]


def test_a_gate_on_the_other_host_that_never_opens_resets_both_hosts():
    shell = FakeShell({"echo ga": "ok", "echo gb": "no"})
    [r] = run(two_host_scenario(), shell, MultiApi(views_ok()))
    assert r.verdict == "ERROR" and "gate never opened on vm-095" in r.problems[0]
    assert ("vm-095", "sudo docker rm -f b") in shell.calls and ("vm-166", "sudo docker rm -f a") in shell.calls


def test_a_command_on_a_host_outside_hosts_is_refused_at_load():
    with pytest.raises(ValueError, match="not in hosts"):
        two_host_scenario(hosts=["vm-166"])
    with pytest.raises(ValueError, match="not in hosts"):
        two_host_scenario(hosts=["vm-166"], start=["x"], reset=["y"], gate=None)   # a request target on vm-095


def test_a_scenario_has_request_and_expect_or_investigations_never_both():
    with pytest.raises(ValueError, match="investigations"):
        two_host_scenario(request={"target": "vm-166/container:x", "reason": "r", "kind": "check"},
                          expect={"outcome": "no_incident"})
    with pytest.raises(ValueError):
        e2e.Scenario.from_dict({"id": "X", "title": "t", "host": "vm-166"})


def test_the_dry_run_names_the_host_of_every_command():
    lines = "\n".join(e2e.describe(two_host_scenario(), ME))
    assert "start [vm-095]: sudo docker start b" in lines and "reset [vm-166]: sudo docker rm -f a" in lines
    assert "gate [vm-095]" in lines and lines.count("investigate:") == 2


# --- the catalogue ----------------------------------------------------------------------------------------------------
def cat():
    return e2e.load_catalogue(CATALOGUE)


def test_every_argus_service_a_scenario_stops_is_started_again_by_its_reset_first():
    """SC-10 and SC-12 stop Argus's own services: the reset starts them before anything else, so a failed run (or a
    failed later reset line) never leaves monitoring or the read path down. `docker start` succeeds on a running
    container, so the reset is idempotent."""
    stopping = 0
    for sc in cat().values():
        stopped = [(c.host, m.group(1)) for c in sc.start for m in [re.search(r"docker stop (argus-v18-[\w-]+)", c)] if m]
        for host, name in stopped:
            stopping += 1
            first = sc.reset[0]
            assert (first.host, str(first)) == (host, f"sudo docker start {name}"), sc.id
    assert stopping >= 2


def test_sc10_is_the_blind_spot_of_vm095_and_vm166_is_unaffected():
    sc = cat()["SC-10"]
    assert [(c.host, str(c)) for c in sc.start] == [("vm-095", "sudo docker stop argus-v18-node-exporter")]
    assert [g.host for g in sc.gates] == ["vm-095"]
    up = e2e.promql_cmd("vm-095", 'up{argus_host="vm-095",job="argus-v18-node-exporter"}')
    assert sc.gates[0].cmd.startswith(up) and sc.gates[0].expect == "==0"
    assert "argus-v18-prometheus" in up                              # vm-095's Prometheus has no host port (E2E-6)
    assert sc.pre_gates[0].expect == "==1"
    blind, other = sc.investigations
    assert blind[0] == {"target": "vm-095/host:vm-095", "reason": blind[0]["reason"], "kind": "check"}
    assert blind[1] == {"outcome": "no_action_escalated", "class": "monitoring_blind_spot", "first_runbook": "RB-014",
                        "model": "none", "reads_on": "vm-095"}
    assert other[0]["target"].startswith("vm-166/") and other[1]["outcome"] == "no_incident"
    assert other[1]["reads_on"] == "vm-166" and set(sc.hosts) == {"vm-095", "vm-166"}


def test_sc12_escalates_on_vm166_without_its_read_gateway_and_vm095_still_answers():
    sc = cat()["SC-12"]
    starts = [(c.host, str(c)) for c in sc.start]
    assert starts[0][0] == "vm-166" and "--profile sc01 up -d argus-lab-worker-oom" in starts[0][1]
    assert starts[1] == ("vm-166", "sudo docker stop argus-v18-read-gateway")
    assert [(c.host, str(c)) for c in sc.reset][0] == ("vm-166", "sudo docker start argus-v18-read-gateway")
    assert any("rm -sf argus-lab-worker-oom" in c for c in sc.reset)
    cut, other = sc.investigations
    assert cut[0]["target"] == "vm-166/container:argus-lab-worker"
    assert cut[1]["if_diagnosed"]["executor_down"] == "docker_read" and cut[1]["reads_on"] == "vm-166"   # E2E-9
    assert other[0]["target"].startswith("vm-095/") and other[1]["outcome"] == "no_incident"


def test_the_identity_proof_runs_sc01_and_sc02_together_and_keeps_each_on_its_host():
    c = cat()
    sc, sc01, sc02 = c["ID-1"], c["SC-01"], c["SC-02"]
    assert [(x.host, str(x)) for x in sc.start] == [("vm-166", sc01.start[0]), ("vm-095", sc02.start[0])]
    assert sorted((x.host, str(x)) for x in sc.reset) == sorted([("vm-166", sc01.reset[0]), ("vm-095", sc02.reset[0])])
    assert [(g.host, g.cmd) for g in sc.gates] == [("vm-166", sc01.gate.cmd), ("vm-095", sc02.gate.cmd)]
    assert [i for i in sc.investigations] == [(sc01.request, sc01.expect), (sc02.request, sc02.expect)]
