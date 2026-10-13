"""T-0023 (phase 12): run the synthetic incidents end to end, N times each, and grade every run.

    python ops/e2e/run.py --list
    python ops/e2e/run.py SC-01 SC-03 --runs 5 --as <github-handle> [--dry-run] [--out FILE]

Runs on the laptop. VM commands go through `ssh argus-vm095` / `ssh argus-vm166` and are ONLY the commands written
in the reviewed catalogue (ops/e2e/scenarios.yaml). The investigation goes through the Argus HTTP API on the usual
SSH tunnel (ARGUS_API, default http://127.0.0.1:18000); the password comes from ARGUS_PASSWORD or a hidden prompt and
is never written or passed to ssh. The runner opens its own tunnel to vm-095 (local port 18001, keepalives) and
reopens it if it drops; `--api URL` uses an existing tunnel instead. A dropped ssh connection is retried; a command that
failed on the VM is not.

One run: the session marker on each touched host is yours -> nonint-check before -> pre-gate (the signal is clean)
-> start -> gate (the signal the detector reads, polled, never a fixed sleep) -> investigate -> wait for the result
-> grade -> reset (always once a start was attempted, also after an error) -> nonint-check after. A command or a gate
may run on another host than the scenario's (E2E-8), and a run may send several investigations together; each is
graded and the run passes only when all of them do. A host that does
not say NO INTERFERENCE, or a failed reset, stops the whole batch. A wrong diagnosis is a FAIL of that run; the batch
goes on. An incident view without evidence and audit (the runner's user is not an operator) is an ERROR, never a
PASS. Each run is written as one JSON line (default ~/argus-e2e/, outside the repository).
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

CATALOGUE = Path(__file__).resolve().with_name("scenarios.yaml")
SSH_ALIAS = {"vm-095": "argus-vm095", "vm-166": "argus-vm166"}
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4"]
NONINT = "sudo bash /opt/argus-v18/app/ops/nonint-check.sh {label} | tail -1"
PROM = "http://127.0.0.1:18090/api/v1/query"                    # each host's own Prometheus (loopback)
# E2E-6: vm-095's Prometheus publishes no host port (compose.core-join.yml): query it inside its container
PROM_IN_CONTAINER = {"vm-095": "argus-v18-prometheus"}
PROM_VALUE = ("python3 -c 'import json,sys; r=json.load(sys.stdin)[\"data\"][\"result\"]; "
              "print(r[0][\"value\"][1] if r else \"none\")'")
SCENARIO_KEYS = {"id", "title", "host", "hosts", "start", "pre_gate", "gate", "request", "expect", "investigations",
                 "reset"}
GATE_KEYS = {"cmd", "promql", "expect", "timeout_s", "every_s", "host"}
EXPECT_KEYS = {"outcome", "class", "root_cause", "first_runbook", "model", "reads_on", "findings_any"}
FINAL = ("closed", "escalated")
NEEDS_OPERATOR = ("evidence", "audit")      # the API shows them only to operators and approvers


class BatchStop(Exception):
    """Stop everything: a host was disturbed, a reset failed, or the session is not ours. `results` holds the runs
    finished so far (the run that stopped the batch included), so they are still written."""

    def __init__(self, msg: str, result: "RunResult | None" = None):
        super().__init__(msg)
        self.result = result
        self.results: list[RunResult] = []


Shell = Callable[[str, str, float], "tuple[int, str]"]


# --- the catalogue ---------------------------------------------------------------------------------------------------
def promql_cmd(host: str, promql: str) -> str:
    """The command that asks `host`'s own Prometheus for `promql` (a JSON answer on stdout)."""
    container = PROM_IN_CONTAINER.get(host)
    if container is None:
        return f"curl -s --data-urlencode {shlex.quote('query=' + promql)} {PROM}"
    url = "http://127.0.0.1:9090/api/v1/query?query=" + urllib.parse.quote(promql, safe="")
    return f"sudo docker exec {container} wget -qO- {shlex.quote(url)}"


@dataclass
class Gate:
    cmd: str
    expect: str
    timeout_s: float = 180
    every_s: float = 10
    host: str = "vm-166"

    @classmethod
    def from_dict(cls, sid: str, raw: dict | None, host: str = "vm-166") -> "Gate | None":
        if raw is None:
            return None
        unknown = set(raw) - GATE_KEYS
        if unknown:
            raise ValueError(f"{sid}: unknown gate keys {sorted(unknown)}")
        if ("cmd" in raw) == ("promql" in raw):
            raise ValueError(f"{sid}: a gate has exactly one of cmd / promql")
        host = raw.get("host", host)
        if host not in SSH_ALIAS:
            raise ValueError(f"{sid}: unknown host {host}")
        cmd = raw.get("cmd") or f"{promql_cmd(host, raw['promql'])} | {PROM_VALUE}"
        return cls(cmd, str(raw["expect"]), float(raw.get("timeout_s", 180)), float(raw.get("every_s", 10)), host)

    @classmethod
    def list_from(cls, sid: str, raw: dict | list | None, host: str) -> "list[Gate]":
        """One gate, or a list of gates (E2E-8: each may name its own `host`)."""
        return [cls.from_dict(sid, g, host) for g in ([] if raw is None else raw if isinstance(raw, list) else [raw])]

    def opens(self, out: str) -> bool:
        last = (out.strip().splitlines() or [""])[-1].strip()
        m = re.fullmatch(r"(>=|<=|==|>|<)\s*(-?[0-9.]+)", self.expect)
        if m:
            try:
                v = float(last)
            except ValueError:
                return False
            n = float(m.group(2))
            return {">=": v >= n, "<=": v <= n, "==": v == n, ">": v > n, "<": v < n}[m.group(1)]
        return re.search(self.expect, last) is not None


class Cmd(str):
    """A catalogued command and the host it runs on: `"..."` on the scenario's host, or `{host: ..., run: "..."}`
    (not `on`: YAML 1.1 reads that key as true)."""

    host: str

    def __new__(cls, raw: "str | dict", default_host: str, sid: str) -> "Cmd":
        if isinstance(raw, dict):
            if set(raw) != {"host", "run"}:
                raise ValueError(f"{sid}: a command is a string or {{host, run}}")
            raw, default_host = raw["run"], raw["host"]
        if default_host not in SSH_ALIAS:
            raise ValueError(f"{sid}: unknown host {default_host}")
        c = super().__new__(cls, raw)
        c.host = default_host
        return c


def _investigation(sid: str, req: dict, exp: dict) -> "tuple[dict, dict]":
    if set(req) != {"target", "reason", "kind"} or req["kind"] not in ("check", "report"):
        raise ValueError(f"{sid}: request needs exactly target, reason, kind (check|report)")
    if set(exp) - EXPECT_KEYS or "outcome" not in exp:
        raise ValueError(f"{sid}: expect needs an outcome and only {sorted(EXPECT_KEYS)}")
    return req, exp


@dataclass
class Scenario:
    id: str
    title: str
    host: str
    investigations: list[tuple[dict, dict]]          # (request, expect): sent together, each graded
    hosts: list[str] = field(default_factory=list)
    start: list[Cmd] = field(default_factory=list)
    reset: list[Cmd] = field(default_factory=list)
    pre_gates: list[Gate] = field(default_factory=list)
    gates: list[Gate] = field(default_factory=list)

    @property
    def request(self) -> dict:
        return self.investigations[0][0]

    @property
    def expect(self) -> dict:
        return self.investigations[0][1]

    @property
    def pre_gate(self) -> Gate | None:
        return self.pre_gates[0] if self.pre_gates else None

    @property
    def gate(self) -> Gate | None:
        return self.gates[0] if self.gates else None

    @classmethod
    def from_dict(cls, raw: dict) -> "Scenario":
        sid = raw.get("id", "?")
        unknown = set(raw) - SCENARIO_KEYS
        if unknown:
            raise ValueError(f"{sid}: unknown keys {sorted(unknown)}")
        for key in ("title", "host"):
            if key not in raw:
                raise ValueError(f"{sid}: missing {key}")
        if raw["host"] not in SSH_ALIAS:
            raise ValueError(f"{sid}: unknown host {raw['host']}")
        single = "request" in raw or "expect" in raw
        if single == ("investigations" in raw):
            raise ValueError(f"{sid}: give request and expect, or investigations (a list of them), not both")
        if single:
            if "request" not in raw or "expect" not in raw:
                raise ValueError(f"{sid}: missing {'expect' if 'request' in raw else 'request'}")
            invs = [_investigation(sid, raw["request"], raw["expect"])]
        else:
            if not raw["investigations"] or any(set(i) != {"request", "expect"} for i in raw["investigations"]):
                raise ValueError(f"{sid}: investigations is a list of {{request, expect}}")
            invs = [_investigation(sid, i["request"], i["expect"]) for i in raw["investigations"]]
        hosts = raw.get("hosts") or [raw["host"]]
        if any(h not in SSH_ALIAS for h in hosts):
            raise ValueError(f"{sid}: unknown host in hosts")
        start = [Cmd(c, raw["host"], sid) for c in raw.get("start") or []]
        reset = [Cmd(c, raw["host"], sid) for c in raw.get("reset") or []]
        if bool(start) != bool(reset):
            raise ValueError(f"{sid}: whatever is started must be reset")
        pre_gates = Gate.list_from(sid, raw.get("pre_gate"), raw["host"])
        gates = Gate.list_from(sid, raw.get("gate"), raw["host"])
        # every host a command runs on or an investigation reads is checked (session marker, NO INTERFERENCE)
        touched = ({c.host for c in start + reset} | {g.host for g in pre_gates + gates} | {raw["host"]}
                   | {req["target"].split("/", 1)[0] for req, _ in invs})
        if touched - set(hosts):
            raise ValueError(f"{sid}: {sorted(touched - set(hosts))} not in hosts {hosts}")
        return cls(sid, raw["title"], raw["host"], invs, hosts, start, reset, pre_gates, gates)


def load_catalogue(path: Path = CATALOGUE) -> dict[str, Scenario]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, Scenario] = {}
    for raw in data["scenarios"]:
        sc = Scenario.from_dict(raw)
        if sc.id in out:
            raise ValueError(f"{sc.id}: duplicate id")
        out[sc.id] = sc
    return out


# --- grading -----------------------------------------------------------------------------------------------------------
def first_runbook(inc: dict) -> str | None:
    for a in inc.get("audit") or []:
        if a.get("event") == "recall.passages":
            passages = (a.get("detail") or {}).get("passages") or []
            return passages[0].get("runbook_id") if passages else None
    return None


def grade(expect: dict, inc: dict) -> list[str]:
    """What differs from the expectation (empty = PASS). Without `evidence` and `audit` the host, model and runbook
    checks would pass on nothing, so a view without them is never a PASS."""
    missing = [k for k in NEEDS_OPERATOR if k not in inc]
    problems = [f"the incident view has no {' and no '.join(missing)}: the runner's Argus user needs the operator "
                f"role"] if missing else []
    want = expect["outcome"]
    wanted = want if isinstance(want, list) else [want]
    if inc.get("outcome") not in wanted:
        problems.append(f"outcome {inc.get('outcome')!r}, expected {' or '.join(map(repr, wanted))}")
    if "class" in expect and inc.get("incident_class") != expect["class"]:
        problems.append(f"class {inc.get('incident_class')!r}, expected {expect['class']!r}")
    if "root_cause" in expect and inc.get("root_cause_target") != expect["root_cause"]:
        problems.append(f"root cause {inc.get('root_cause_target')!r}, expected {expect['root_cause']!r}")
    if "first_runbook" in expect and first_runbook(inc) != expect["first_runbook"]:
        problems.append(f"first runbook {first_runbook(inc)!r}, expected {expect['first_runbook']!r}")
    if expect.get("model") == "none":
        if inc.get("strategy") == "model_loop" or any(e.get("caller") == "model" for e in inc.get("evidence") or []):
            problems.append("a model call where none is allowed")
    if "reads_on" in expect:
        prefix = f"{expect['reads_on']}/"
        for e in inc.get("evidence") or []:
            t = e.get("target")
            if t and not t.startswith(prefix):
                problems.append(f"read on another host: {t} ({e.get('capability')})")
    if expect.get("findings_any"):
        text = " ".join([*(inc.get("findings") or []), inc.get("diagnosis") or ""]).lower()
        if not any(s.lower() in text for s in expect["findings_any"]):
            problems.append(f"none of {expect['findings_any']} in the findings or the diagnosis")
    return problems


# --- running -----------------------------------------------------------------------------------------------------------
@dataclass
class RunResult:
    scenario: str
    run: int
    runs: int
    verdict: str                     # PASS | FAIL | ERROR
    problems: list[str]
    incident_id: str | None = None
    outcome: str | None = None
    incident_class: str | None = None
    root_cause_target: str | None = None
    first_runbook: str | None = None
    duration_s: float = 0
    started_at: str = ""
    investigations: list[dict] = field(default_factory=list)   # one per investigation; the first is also above


def ssh(host: str, cmd: str, timeout_s: float = 120, attempts: int = 4, wait_s: float = 15) -> tuple[int, str]:
    """Run one catalogued command on a VM. rc 255 (ssh could not connect) and a timeout are retried; any other rc is
    the command's own answer and is returned as it is (a failed command is never repeated)."""
    rc, out = 255, ""
    for attempt in range(attempts):
        try:
            r = subprocess.run(["ssh", *SSH_OPTS, SSH_ALIAS[host], cmd], capture_output=True, text=True,
                               timeout=timeout_s)
            rc, out = r.returncode, (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            rc, out = 124, "timeout"
        if rc not in (124, 255):
            return rc, out
        if attempt < attempts - 1:
            time.sleep(wait_s)
    return rc, out


def _wait(gate: Gate, shell: Shell, now, sleep) -> tuple[bool, str]:
    deadline, out = now() + gate.timeout_s, ""
    while True:
        _, out = shell(gate.host, gate.cmd, 60)
        if gate.opens(out):
            return True, out
        if now() >= deadline:
            return False, out
        sleep(gate.every_s)


def run_once(sc: Scenario, i: int, runs: int, shell: Shell, api, me: str, now, sleep,
             investigate_timeout_s: float = 600, poll_s: float = 5) -> RunResult:
    t0 = now()
    res = RunResult(sc.id, i, runs, "ERROR", [], started_at=dt.datetime.now(dt.timezone.utc).isoformat())
    for h in sc.hosts:
        rc, out = shell(h, f"grep -q '^holder={me} ' /opt/argus-v18/SESSION && echo 'SESSION OK' "
                           f"|| echo 'NOT YOUR SESSION'", 30)
        if "SESSION OK" not in out:
            raise BatchStop(f"{sc.id}: the session marker on {h} is not {me}'s ({out[:80]})")
    for h in sc.hosts:
        shell(h, NONINT.format(label="before"), 180)
    started = False                             # reset only what a start may have created
    try:
        on = (lambda g: f" on {g.host}") if len({g.host for g in sc.pre_gates + sc.gates}) > 1 else (lambda g: "")
        for g in sc.pre_gates:
            ok, out = _wait(g, shell, now, sleep)
            if not ok:
                res.problems.append(f"pre-gate never clean{on(g)}: last {out[-60:]!r}, wanted {g.expect}")
                return res
        for cmd in sc.start:
            started = True
            rc, out = shell(cmd.host, cmd, 300)
            if rc != 0:
                res.problems.append(f"start failed (rc {rc}) on {cmd.host}: {cmd} -> {out[-200:]}")
                return res
        for g in sc.gates:
            ok, out = _wait(g, shell, now, sleep)
            if not ok:
                res.problems.append(f"gate never opened{on(g)}: last {out[-60:]!r}, wanted {g.expect}")
                return res
        # E2E-8: every investigation is sent before the first is polled (the identity proof needs them together)
        iids = [api.investigate(req["target"], req["reason"], req["kind"]) for req, _ in sc.investigations]
        res.incident_id = iids[0]
        deadline, views = now() + investigate_timeout_s, {}
        while True:
            for iid in iids:
                if views.get(iid, {}).get("status") not in FINAL:
                    views[iid] = api.incident(iid)
            if all(v.get("status") in FINAL for v in views.values()):
                break
            if now() >= deadline:
                late = ", ".join(f"{i} {v.get('status')}" for i, v in views.items() if v.get("status") not in FINAL)
                res.problems.append(f"no result within {investigate_timeout_s:.0f} s (status {late})")
                return res
            sleep(poll_s)
        several = len(iids) > 1
        for iid, (req, exp) in zip(iids, sc.investigations):
            inc = views[iid]
            problems = grade(exp, inc)
            res.investigations.append({"target": req["target"], "incident_id": iid, "outcome": inc.get("outcome"),
                                       "incident_class": inc.get("incident_class"),
                                       "root_cause_target": inc.get("root_cause_target"),
                                       "first_runbook": first_runbook(inc), "problems": problems})
            res.problems += [f"{req['target']}: {p}" if several else p for p in problems]
        first = res.investigations[0]
        res.outcome, res.incident_class = first["outcome"], first["incident_class"]
        res.root_cause_target, res.first_runbook = first["root_cause_target"], first["first_runbook"]
        if any(k not in v for v in views.values() for k in NEEDS_OPERATOR):
            return res                          # ERROR: nothing was graded, so not a FAIL of the diagnosis either
        res.verdict = "FAIL" if res.problems else "PASS"
        return res
    except BatchStop:
        raise
    except Exception as e:          # noqa: BLE001 - an error of this run, reported; the reset below still runs
        res.problems.append(f"error: {e!r}"[:300])
        return res
    finally:
        res.duration_s = round(now() - t0, 1)
        failed = [cmd for cmd in (sc.reset if started else []) if shell(cmd.host, cmd, 300)[0] != 0]
        disturbed = [h for h in sc.hosts if "NO INTERFERENCE" not in shell(h, NONINT.format(label="after"), 180)[1]]
        if failed:
            res.problems.append(f"reset failed: {failed}")
            raise BatchStop(f"{sc.id} run {i}: reset failed: {failed} - fix by hand before anything else", res)
        if disturbed:
            res.problems.append(f"NO INTERFERENCE missing on {disturbed}")
            raise BatchStop(f"{sc.id} run {i}: NO INTERFERENCE missing on {disturbed} - stop and read nonint-check",
                            res)


def run_batch(scenarios: list[Scenario], runs: int, shell: Shell, api, me: str, now=time.monotonic,
              sleep=time.sleep, log: Callable[[str], None] = print) -> list[RunResult]:
    results: list[RunResult] = []
    for sc in scenarios:
        for i in range(1, runs + 1):
            try:
                r = run_once(sc, i, runs, shell, api, me, now, sleep)
            except BatchStop as e:
                e.results = results + ([e.result] if e.result else [])
                raise
            results.append(r)
            log(f"{sc.id} run {i}/{runs} {r.verdict} ({r.incident_id or '-'}, {r.duration_s:.0f} s)"
                + "".join(f"\n    - {p}" for p in r.problems))
    return results


def write_results(results: list[RunResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def summary(results: list[RunResult]) -> list[str]:
    lines = [f"{'scenario':<10}{'runs':>5}{'pass':>6}{'fail':>6}{'error':>7}"]
    for sid in dict.fromkeys(r.scenario for r in results):
        rs = [r for r in results if r.scenario == sid]
        n = {v: sum(r.verdict == v for r in rs) for v in ("PASS", "FAIL", "ERROR")}
        lines.append(f"{sid:<10}{len(rs):>5}{n['PASS']:>6}{n['FAIL']:>6}{n['ERROR']:>7}")
    return lines


# --- the Argus API (through the SSH tunnel) ----------------------------------------------------------------------------
class Tunnel:
    """The runner's own SSH tunnel to the Argus API on vm-095, kept alive and reopened if it dies."""

    def __init__(self, port: int = 18001, sleep=time.sleep):
        self.port, self.sleep, self.proc = port, sleep, None
        self.base = f"http://127.0.0.1:{port}"

    def ensure(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            return
        self.close()
        self.proc = subprocess.Popen(["ssh", "-N", *SSH_OPTS, "-o", "ExitOnForwardFailure=yes",
                                      "-L", f"{self.port}:127.0.0.1:18000", SSH_ALIAS["vm-095"]],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            if healthz(self.base):
                return
            self.sleep(1)

    def close(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None


class Api:
    def __init__(self, base: str, user: str, password: str, reconnect: Callable[[], None] = lambda: None,
                 attempts: int = 8, wait_s: float = 15, sleep=time.sleep):
        self.base, self.user, self._password, self.token = base.rstrip("/"), user, password, None
        self.reconnect, self.attempts, self.wait_s, self.sleep = reconnect, attempts, wait_s, sleep
        self._login()

    def _login(self) -> None:
        body = urllib.parse.urlencode({"username": self.user, "password": self._password}).encode()
        self.token = self._req("POST", "/api/v1/auth/token", body, form=True, retry=False)["access_token"]

    def _req(self, method: str, path: str, body: bytes | None = None, form: bool = False, retry: bool = True):
        r = urllib.request.Request(self.base + path, data=body, method=method)
        r.add_header("Content-Type", "application/x-www-form-urlencoded" if form else "application/json")
        if self.token:
            r.add_header("Authorization", f"Bearer {self.token}")
        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(r, timeout=30) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code == 401 and retry:            # the token lasts 30 minutes; a batch can last longer
                    self._login()
                    return self._req(method, path, body, form, retry=False)
                raise
            except urllib.error.URLError:              # the tunnel dropped: reopen it, wait, try again (~2 min)
                if attempt == self.attempts - 1:
                    raise
                self.reconnect()
                self.sleep(self.wait_s)

    def investigate(self, target: str, reason: str, kind: str) -> str:
        body = json.dumps({"target": target, "reason": reason, "request_kind": kind}).encode()
        return self._req("POST", "/api/v1/investigations", body)["incident_id"]

    def incident(self, iid: str) -> dict:
        return self._req("GET", f"/api/v1/incidents/{iid}")


def healthz(base: str) -> bool:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/healthz", timeout=10) as resp:
            return json.loads(resp.read()).get("ok") is True
    except (OSError, ValueError):
        return False


# --- command line ------------------------------------------------------------------------------------------------------
def describe(sc: Scenario, me: str) -> list[str]:
    lines = [f"== {sc.id}: {sc.title}  (host {sc.host}; touched: {', '.join(sc.hosts)})",
             f"  session marker must be holder={me} on {', '.join(sc.hosts)}; nonint-check before"]
    lines += [f"  pre-gate [{g.host}] until {g.expect} (max {g.timeout_s:.0f} s): {g.cmd}" for g in sc.pre_gates]
    lines += [f"  start [{c.host}]: {c}" for c in sc.start]
    lines += [f"  gate [{g.host}] until {g.expect} (max {g.timeout_s:.0f} s): {g.cmd}" for g in sc.gates]
    for req, exp in sc.investigations:
        lines += [f"  investigate: {json.dumps(req)}", f"  expect: {json.dumps(exp)}"]
    lines += [f"  reset [{c.host}]: {c}" for c in sc.reset]
    lines.append("  nonint-check after (NO INTERFERENCE, or the batch stops)")
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ops/e2e/run.py", description=__doc__.split("\n\n")[0])
    p.add_argument("ids", nargs="*", help="scenario ids from the catalogue, e.g. SC-01 SC-03")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--as", dest="me", help="your GitHub handle (the session marker and the Argus user)")
    p.add_argument("--api", default=os.getenv("ARGUS_API"), help="use this API (an open tunnel) instead of the "
                   "runner's own tunnel to vm-095")
    p.add_argument("--tunnel-port", type=int, default=18001)
    p.add_argument("--catalogue", type=Path, default=CATALOGUE)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true", help="print every step; run nothing")
    p.add_argument("--list", action="store_true")
    a = p.parse_args(argv)
    cat = load_catalogue(a.catalogue)
    if a.list:
        for sc in cat.values():
            print(f"{sc.id:<6} {sc.host}  {sc.title}")
        return 0
    unknown = [i for i in a.ids if i not in cat]
    if not a.ids or unknown or not a.me or not re.fullmatch(r"[A-Za-z0-9-]+", a.me) or a.runs < 1:
        print(f"usage: give scenario ids (unknown: {unknown}), --as <github-handle>, --runs >= 1", file=sys.stderr)
        return 2
    chosen = [cat[i] for i in a.ids]
    if a.dry_run:
        for sc in chosen:
            print("\n".join(describe(sc, a.me)))
        print(f"(dry run: {a.runs} run(s) each; nothing was executed)")
        return 0
    tunnel = None if a.api else Tunnel(a.tunnel_port)
    base = a.api or tunnel.base
    if tunnel:
        tunnel.ensure()
    try:
        return _batch(a, chosen, base, tunnel)
    finally:
        if tunnel:
            tunnel.close()


def _batch(a, chosen: list[Scenario], base: str, tunnel: "Tunnel | None") -> int:
    if not healthz(base):
        print(f"cannot reach Argus at {base}" + ("" if tunnel else ": is the tunnel open?"), file=sys.stderr)
        return 2
    password = os.getenv("ARGUS_PASSWORD") or getpass.getpass(f"Argus password for {a.me}: ")
    api = Api(base, a.me, password, reconnect=tunnel.ensure if tunnel else (lambda: None))
    out = a.out or Path.home() / "argus-e2e" / f"{dt.datetime.now():%Y%m%d-%H%M%S}.jsonl"
    results: list[RunResult] = []
    stopped = None
    try:
        results = run_batch(chosen, a.runs, ssh, api, a.me)
    except BatchStop as e:
        results, stopped = e.results, str(e)
    write_results(results, out)
    print("\n".join(summary(results)))
    print(f"results: {out}")
    if stopped:
        print(f"BATCH STOPPED: {stopped}")
        return 3
    return 0 if all(r.verdict == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
