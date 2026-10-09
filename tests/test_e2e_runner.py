"""T-0023 (phase 12): the end-to-end scenario runner, `ops/e2e/run.py`, with its catalogue `ops/e2e/scenarios.yaml`.

Offline: a fake ssh (records every command, answers from a script) and a fake Argus API. The runner must run the
catalogued commands only, wait on a gate instead of sleeping, always reset, stop the batch on interference or a failed
reset, and grade each incident (outcome, class, root cause, first runbook, model use, host of every read).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "ops" / "e2e" / "scenarios.yaml"


def _load():
    spec = importlib.util.spec_from_file_location("e2e_run", ROOT / "ops" / "e2e" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["e2e_run"] = mod
    spec.loader.exec_module(mod)
    return mod


e2e = _load()

ME = "tester"
NONINT_OK = "NO INTERFERENCE: non-Argus objects unchanged"


class FakeShell:
    """(host, cmd) -> (rc, out). `answers` maps a substring of the command to an output (or a list, used in turn)."""

    def __init__(self, answers: dict | None = None, fail: set[str] | None = None):
        self.calls: list[tuple[str, str]] = []
        self.answers = {"SESSION": "SESSION OK", "nonint-check.sh before": "saved before.txt (5 lines)",
                        "nonint-check.sh after": NONINT_OK, **(answers or {})}
        self.fail = fail or set()

    def __call__(self, host: str, cmd: str, timeout_s: float = 0) -> tuple[int, str]:
        self.calls.append((host, cmd))
        if any(f in cmd for f in self.fail):
            return 1, "boom"
        for key, out in self.answers.items():
            if key in cmd:
                if isinstance(out, list):
                    return 0, out.pop(0) if len(out) > 1 else out[0]
                return 0, out
        return 0, ""

    def cmds(self) -> list[str]:
        return [c for _, c in self.calls]


class FakeApi:
    def __init__(self, incident: dict):
        self.incident_view = incident
        self.requests: list[dict] = []

    def investigate(self, target: str, reason: str, kind: str) -> str:
        self.requests.append({"target": target, "reason": reason, "kind": kind})
        return self.incident_view["id"]

    def incident(self, iid: str) -> dict:
        return self.incident_view


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def incident(**kw) -> dict:
    base = {"id": "inc_test", "status": "closed", "outcome": "diagnosed", "incident_class": "container_restart_loop",
            "strategy": "model_loop", "root_cause_target": "vm-166/container:argus-lab-worker", "findings": [],
            "diagnosis": "killed by its own memory limit",
            "evidence": [{"target": "vm-166/container:argus-lab-worker", "caller": "model", "capability": "container.status"}],
            "audit": [{"event": "recall.passages", "detail": {"passages": [{"runbook_id": "RB-001"}, {"runbook_id": "RB-008"}]}}]}
    base.update(kw)
    return base


def scenario(**kw):
    raw = {"id": "SC-T", "title": "test", "host": "vm-166",
           "start": ["sudo docker start x"],
           "gate": {"cmd": "echo restarts", "expect": "^[3-9]$", "timeout_s": 60, "every_s": 10},
           "request": {"target": "vm-166/container:argus-lab-worker", "reason": "keeps restarting", "kind": "report"},
           "expect": {"outcome": "diagnosed", "class": "container_restart_loop", "first_runbook": "RB-001",
                      "reads_on": "vm-166"},
           "reset": ["sudo docker rm -f x"]}
    raw.update(kw)
    return e2e.Scenario.from_dict(raw)


def run(sc, shell, api, runs=1, clock=None):
    clock = clock or Clock()
    return e2e.run_batch([sc], runs, shell, api, ME, now=clock.now, sleep=clock.sleep, log=lambda line: None)


# --- the catalogue ---------------------------------------------------------------------------------------------------
def test_the_catalogue_loads_with_the_verified_scenarios():
    cat = e2e.load_catalogue(CATALOGUE)
    assert {"H-1", "H-2", "SC-01", "SC-02", "SC-03", "SC-07", "SC-09", "SC-11"} <= set(cat)
    for sc in cat.values():
        assert sc.host in ("vm-095", "vm-166") and sc.request["kind"] in ("check", "report")
        assert sc.expect.get("outcome"), sc.id
        assert bool(sc.start) == bool(sc.reset), f"{sc.id}: whatever is started must be reset"


def test_the_catalogue_refuses_unknown_keys_and_missing_parts(tmp_path):
    with pytest.raises(ValueError, match="unknown"):
        e2e.Scenario.from_dict({"id": "X", "title": "x", "host": "vm-166", "request": {"target": "vm-166/host:vm-166",
                                "reason": "r", "kind": "check"}, "expect": {"outcome": "no_incident"}, "colour": "red"})
    with pytest.raises(ValueError, match="request"):
        e2e.Scenario.from_dict({"id": "X", "title": "x", "host": "vm-166", "expect": {"outcome": "no_incident"}})
    with pytest.raises(ValueError, match="expect"):
        scenario(expect={"outcome": "diagnosed", "colour": "red"})


# --- the grader ------------------------------------------------------------------------------------------------------
def test_the_grader_passes_a_matching_incident():
    assert e2e.grade(scenario().expect, incident()) == []


@pytest.mark.parametrize("change, problem", [
    ({"outcome": "undiagnosable"}, "outcome"),
    ({"incident_class": "dependency_unavailable"}, "class"),
    ({"root_cause_target": "vm-166/container:argus-lab-api"}, "root cause"),
    ({"audit": [{"event": "recall.passages", "detail": {"passages": [{"runbook_id": "RB-008"}]}}]}, "first runbook"),
    ({"evidence": [{"target": "vm-095/container:argus-lab-worker", "caller": "model"}]}, "vm-095"),
])
def test_the_grader_names_what_is_wrong(change, problem):
    exp = {**scenario().expect, "root_cause": "vm-166/container:argus-lab-worker"}
    problems = e2e.grade(exp, incident(**change))
    assert problems and any(problem in p for p in problems), problems


def test_the_grader_refuses_a_model_call_where_none_is_allowed():
    exp = {"outcome": "unsupported_escalated", "model": "none"}
    ok = incident(outcome="unsupported_escalated", strategy=None, incident_class=None,
                  evidence=[{"target": "vm-095/container:argus-lab-api", "caller": "strategy:evidence_pack"}])
    assert e2e.grade(exp, ok) == []
    assert any("model" in p for p in e2e.grade(exp, incident(outcome="unsupported_escalated")))


def test_the_grader_accepts_a_list_of_outcomes_and_a_null_class():
    exp = {"outcome": ["refused"], "class": None}
    assert e2e.grade(exp, incident(outcome="refused", incident_class=None, evidence=[], audit=[])) == []


# --- one run, and the batch --------------------------------------------------------------------------------------------
def test_a_passing_run_follows_the_order_and_always_resets():
    shell, api = FakeShell({"echo restarts": ["1", "3"]}), FakeApi(incident())
    res = run(scenario(), shell, api)
    assert [r.verdict for r in res] == ["PASS"]
    order = shell.cmds()
    idx = [next(i for i, c in enumerate(order) if key in c) for key in
           ("SESSION", "nonint-check.sh before", "docker start x", "echo restarts", "docker rm -f x",
            "nonint-check.sh after")]
    assert idx == sorted(idx), order
    assert api.requests == [{"target": "vm-166/container:argus-lab-worker", "reason": "keeps restarting",
                             "kind": "report"}]


def test_a_gate_that_never_opens_is_an_error_and_the_reset_still_runs():
    shell, api = FakeShell({"echo restarts": "1"}), FakeApi(incident())
    clock = Clock()
    res = run(scenario(), shell, api, clock=clock)
    assert res[0].verdict == "ERROR" and any("gate" in p for p in res[0].problems)
    assert api.requests == []                                       # nothing investigated
    assert any("docker rm -f x" in c for c in shell.cmds())         # reset ran anyway
    assert clock.t >= 60                                            # waited on the gate, then gave up


def test_a_wrong_diagnosis_fails_that_run_and_the_batch_goes_on():
    shell = FakeShell({"echo restarts": "3"})
    res = run(scenario(), shell, FakeApi(incident(incident_class="dependency_unavailable")), runs=2)
    assert [r.verdict for r in res] == ["FAIL", "FAIL"]


def test_interference_stops_the_batch():
    shell = FakeShell({"echo restarts": "3", "nonint-check.sh after": "DIFFERENCES ABOVE (< before, > now)"})
    with pytest.raises(e2e.BatchStop, match="INTERFERENCE"):
        run(scenario(), shell, FakeApi(incident()), runs=3)
    assert sum("docker start x" in c for c in shell.cmds()) == 1   # no second run


def test_a_failed_reset_stops_the_batch():
    shell = FakeShell({"echo restarts": "3"}, fail={"docker rm -f x"})
    with pytest.raises(e2e.BatchStop, match="reset"):
        run(scenario(), shell, FakeApi(incident()), runs=2)


def test_a_session_that_is_not_mine_stops_before_anything_runs():
    shell = FakeShell({"SESSION": "NOT YOUR SESSION"})
    with pytest.raises(e2e.BatchStop, match="session"):
        run(scenario(), shell, FakeApi(incident()))
    assert not any("docker" in c or "nonint" in c for c in shell.cmds())


def test_a_failed_start_is_an_error_and_resets():
    shell = FakeShell(fail={"docker start x"})
    res = run(scenario(), shell, FakeApi(incident()))
    assert res[0].verdict == "ERROR" and any("start" in p for p in res[0].problems)
    assert any("docker rm -f x" in c for c in shell.cmds())


def test_the_session_check_names_the_runner():
    shell = FakeShell({"echo restarts": "3"})
    run(scenario(), shell, FakeApi(incident()))
    session = next(c for c in shell.cmds() if "SESSION" in c)
    assert f"holder={ME} " in session


def test_a_prometheus_gate_queries_the_hosts_own_prometheus():
    sc = scenario(gate={"promql": 'argus_probe_success{owner="argus-lab-api"}', "expect": "^0$", "timeout_s": 60})
    shell = FakeShell({"18090": "0"})
    run(sc, shell, FakeApi(incident()))
    gate = next(c for h, c in shell.calls if "18090" in c)
    assert "127.0.0.1:18090/api/v1/query" in gate and "argus_probe_success" in gate


# --- the command line ----------------------------------------------------------------------------------------------------
def test_the_dry_run_executes_nothing_and_shows_every_step(capsys, monkeypatch):
    def no_ssh(*a, **k):
        raise AssertionError("the dry run must not run anything")
    monkeypatch.setattr(e2e, "ssh", no_ssh)
    assert e2e.main(["SC-01", "--dry-run", "--as", ME]) == 0
    out = capsys.readouterr().out
    assert "SC-01" in out and "--profile sc01" in out and "vm-166/container:argus-lab-worker" in out
    assert "reset" in out.lower()


def test_unknown_scenarios_are_refused(capsys):
    assert e2e.main(["SC-99", "--dry-run", "--as", ME]) == 2


def test_results_are_written_as_json_lines(tmp_path):
    shell = FakeShell({"echo restarts": "3"})
    out = tmp_path / "runs.jsonl"
    res = run(scenario(), shell, FakeApi(incident()), runs=2)
    e2e.write_results(res, out)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["run"] for r in rows] == [1, 2] and rows[0]["verdict"] == "PASS"
    assert rows[0]["incident_id"] == "inc_test" and rows[0]["first_runbook"] == "RB-001"


# --- a dropped connection (step 2, 2026-10-09: the tunnel and then ssh to vm-166 dropped in the middle of SC-01) -----
class _Proc:
    def __init__(self, rc: int, out: str = ""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def test_ssh_retries_a_connection_failure_and_sets_timeouts(monkeypatch):
    seen, answers = [], [_Proc(255, "ssh: connect to host: Connection timed out"), _Proc(0, "SESSION OK")]
    monkeypatch.setattr(e2e.subprocess, "run", lambda args, **k: (seen.append(args), answers.pop(0))[1])
    monkeypatch.setattr(e2e.time, "sleep", lambda s: None)
    assert e2e.ssh("vm-166", "echo hi") == (0, "SESSION OK")
    assert len(seen) == 2
    assert "ConnectTimeout=15" in " ".join(seen[0]) and "ServerAliveInterval=15" in " ".join(seen[0])


def test_ssh_does_not_retry_a_command_that_failed_on_the_vm(monkeypatch):
    seen = []
    monkeypatch.setattr(e2e.subprocess, "run", lambda args, **k: (seen.append(args), _Proc(1, "boom"))[1])
    monkeypatch.setattr(e2e.time, "sleep", lambda s: None)
    assert e2e.ssh("vm-166", "false")[0] == 1 and len(seen) == 1


def test_the_api_retries_a_dropped_connection_after_reopening_the_tunnel(monkeypatch):
    import io
    import urllib.error
    calls, reconnects = [], []

    def urlopen(req, timeout=30):
        calls.append(req.full_url)
        if len(calls) in (2, 3):                                     # the tunnel dropped twice after the login
            raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
        body = {"access_token": "t"} if req.full_url.endswith("/token") else {"id": "inc_x", "status": "closed"}
        return io.BytesIO(json.dumps(body).encode())
    monkeypatch.setattr(e2e.urllib.request, "urlopen", urlopen)
    api = e2e.Api("http://127.0.0.1:18001", ME, "pw", reconnect=lambda: reconnects.append(1), sleep=lambda s: None)
    assert api.incident("inc_x")["status"] == "closed"
    assert len(reconnects) == 2


def test_the_api_gives_up_after_its_retries(monkeypatch):
    import io
    import urllib.error

    def urlopen(req, timeout=30):
        if req.full_url.endswith("/token"):
            return io.BytesIO(b'{"access_token": "t"}')
        raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", urlopen)
    api = e2e.Api("http://127.0.0.1:18001", ME, "pw", reconnect=lambda: None, sleep=lambda s: None)
    with pytest.raises(e2e.urllib.error.URLError):
        api.incident("inc_x")


def test_the_runner_keeps_its_own_tunnel_alive(monkeypatch):
    started = []

    class P:
        def __init__(self, args, **k):
            started.append(args)
            self.dead = False

        def poll(self):
            return 255 if self.dead else None

        def terminate(self):
            self.dead = True

        def wait(self, timeout=None):
            return 0
    monkeypatch.setattr(e2e.subprocess, "Popen", P)
    monkeypatch.setattr(e2e, "healthz", lambda base: True)
    t = e2e.Tunnel(18001, sleep=lambda s: None)
    t.ensure()
    assert len(started) == 1
    args = " ".join(started[0])
    assert "-N" in started[0] and "18001:127.0.0.1:18000" in args and "argus-vm095" in args
    assert "ExitOnForwardFailure=yes" in args and "ServerAliveInterval=15" in args
    t.ensure()                                                      # alive: nothing new
    assert len(started) == 1
    t.proc.dead = True                                              # the tunnel died
    t.ensure()
    assert len(started) == 2
    t.close()
