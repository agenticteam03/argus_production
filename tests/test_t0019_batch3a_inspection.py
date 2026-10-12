"""T-0019 batch 3a: the inspection policy (ARCHITECTURE §4.7) as data, checked before any file, journal or process read.

Batch 3b adds the host-probe verbs that read files, service configuration, the journal (rsyslog's text copy) and process
details. Before any of them exists, the policy says what each target may have read: path allowlists per target, a deny
list that always wins (with a built-in floor the data cannot remove), bounded journal reads, process details per host,
and `arbitrary_exec: false`. The agent checks it before execution (audited refusal, rule `inspection`); the probe gets
the same data in its rendered config and re-checks it (3b). Decided 2026-10-12 (`conantkd`): `files` starts empty.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from argus.domain.model import TargetRef
from argus.policy.engine import PolicyEngine
from argus.policy.inspection import BUILTIN_DENY, InspectionPolicy

ROOT = Path(__file__).resolve().parents[1]
NGINX = TargetRef.parse("vm-166/container:argus-lab-nginx")
HOST166 = TargetRef.parse("vm-166/host:vm-166")
HOST095 = TargetRef.parse("vm-095/host:vm-095")
NGINX_CONF = "/opt/argus-v18/app/deploy/lab/nginx/default.conf"


def _policy(**over) -> InspectionPolicy:
    data = {"targets": {"vm-166/host:vm-166": {"files": ["/var/log/myapp/"], "processes": True,
                                               "journal": {"units": ["docker.service"], "max_lines": 200}},
                        "vm-166/container:argus-lab-nginx": {"service_config": [NGINX_CONF]}},
            "deny": ["*token*"], "limits": {"max_lines": 500, "max_bytes": 65536}, "arbitrary_exec": False}
    data.update(over)
    return InspectionPolicy.from_data(data)


# --- the policy file -------------------------------------------------------------------------------------------------

def test_the_policy_file_declares_the_inspection_policy():
    raw = (ROOT / "config" / "policy.yaml").read_text(encoding="utf-8")
    eng = PolicyEngine(yaml.safe_load(raw), raw)
    ins = eng.inspection
    assert ins.arbitrary_exec is False
    assert ins.allows(NGINX, "host.service_config", {"path": NGINX_CONF}).allowed
    for t in (HOST166, HOST095, NGINX):                    # decided: no file is readable yet
        assert not ins.allows(t, "host.read_file", {"path": "/var/log/syslog"}).allowed
    assert ins.allows(HOST166, "host.journal", {"unit": "docker.service", "lines": 100}).allowed
    assert ins.allows(HOST095, "host.process_details", {"pid": 1}).allowed
    for d in ("environment_variables", "/run/secrets/", "/opt/argus-v18/secrets/", "/root/", "*.key", "*.pem", ".env"):
        assert d in ins.deny


def test_arbitrary_exec_can_never_be_enabled():
    with pytest.raises(ValueError, match="arbitrary_exec"):
        _policy(arbitrary_exec=True)
    with pytest.raises(ValueError, match="arbitrary_exec"):
        _policy(arbitrary_exec="false")                    # a string is not false
    assert InspectionPolicy.from_data({}).arbitrary_exec is False           # absent = false, nothing allowed


@pytest.mark.parametrize("bad", [
    {"targets": {"vm-166/host:vm-166": {"filez": ["/x/"]}}},                 # a typo fails closed
    {"targets": {"not-a-target": {"processes": True}}},
    {"targets": {"vm-166/host:vm-166": {"files": ["relative/path"]}}},
    {"targets": {"vm-166/host:vm-166": {"files": ["/var/log/../../etc/"]}}},
    {"targets": {"vm-166/host:vm-166": {"journal": {"units": ["docker.service; rm -rf /"], "max_lines": 10}}}},
    {"targets": {"vm-166/host:vm-166": {"journal": {"units": ["docker.service"], "max_lines": 100000}}}},
    {"targets": {"vm-166/host:vm-166": {"processes": "yes"}}},
    {"unknown_section": 1},
])
def test_a_malformed_policy_refuses_to_load(bad):
    with pytest.raises(ValueError):
        InspectionPolicy.from_data(bad)


# --- decisions -------------------------------------------------------------------------------------------------------

def test_paths_are_allowed_only_inside_their_entries():
    p = _policy()
    assert p.allows(HOST166, "host.read_file", {"path": "/var/log/myapp/app.log"}).allowed
    assert p.allows(NGINX, "host.service_config", {"path": NGINX_CONF}).allowed
    for path in ("/var/log/myapp", "/var/log/myapp2/x.log", "/var/log/other.log",       # outside the directory entry
                 NGINX_CONF + ".bak", "/opt/argus-v18/app/deploy/lab/nginx/"):           # an exact entry is exact
        assert not p.allows(HOST166 if "myapp" in path or "other" in path else NGINX,
                            "host.read_file" if "/var/log" in path else "host.service_config", {"path": path}).allowed
    # one target's entries never serve another target, and a kind's entries never serve another kind
    assert not p.allows(HOST095, "host.read_file", {"path": "/var/log/myapp/app.log"}).allowed
    assert not p.allows(HOST166, "host.service_config", {"path": "/var/log/myapp/app.log"}).allowed
    assert not p.allows(NGINX, "host.read_file", {"path": NGINX_CONF}).allowed


@pytest.mark.parametrize("path", ["/var/log/myapp/../../../etc/passwd", "/var/log/myapp/./a.log", "var/log/myapp/a",
                                  "/var/log/myapp//a.log", "/var/log/myapp/a\x00.log", "", None, 7])
def test_unnormalized_paths_are_refused_not_normalized(path):
    d = _policy().allows(HOST166, "host.read_file", {"path": path})
    assert not d.allowed and d.rule == "inspection"


@pytest.mark.parametrize("path", ["/var/log/myapp/server.key", "/var/log/myapp/cert.pem", "/var/log/myapp/.env",
                                  "/var/log/myapp/api_token.txt", "/var/log/myapp/DB_PASSWORD"])
def test_deny_wins_over_an_allow_entry(path):
    d = _policy().allows(HOST166, "host.read_file", {"path": path})
    assert not d.allowed and "deny" in d.reason


def test_the_built_in_deny_floor_cannot_be_removed_by_the_data():
    p = _policy(deny=[], targets={"vm-166/host:vm-166": {"files": ["/run/secrets/", "/opt/argus-v18/", "/root/"]}})
    assert set(BUILTIN_DENY) <= set(p.deny)
    for path in ("/run/secrets/db", "/opt/argus-v18/secrets/agent/vm-166/host_probe_token", "/root/.bashrc"):
        assert not p.allows(HOST166, "host.read_file", {"path": path}).allowed, path
    assert p.allows(HOST166, "host.read_file", {"path": "/opt/argus-v18/DEPLOYED"}).allowed


def test_journal_reads_are_bounded_to_listed_units():
    p = _policy()
    assert p.allows(HOST166, "host.journal", {"unit": "docker.service", "lines": 200}).allowed
    assert not p.allows(HOST166, "host.journal", {"unit": "docker.service", "lines": 201}).allowed   # above the unit's max
    assert not p.allows(HOST166, "host.journal", {"unit": "ssh.service", "lines": 10}).allowed
    assert not p.allows(HOST095, "host.journal", {"unit": "docker.service", "lines": 10}).allowed    # no entry for it
    assert not p.allows(HOST166, "host.journal", {"unit": "docker.service", "lines": 0}).allowed


def test_process_details_only_where_declared():
    p = _policy()
    assert p.allows(HOST166, "host.process_details", {"pid": 4242}).allowed
    assert not p.allows(HOST095, "host.process_details", {"pid": 4242}).allowed
    assert not p.allows(NGINX, "host.process_details", {"pid": 4242}).allowed


def test_capabilities_outside_the_inspection_policy_are_not_its_business():
    assert _policy().allows(HOST095, "host.cpu", {}).allowed


# --- the engine and the guarded entry point --------------------------------------------------------------------------

def _engine(**ins) -> PolicyEngine:
    data = {"profile": "production", "max_tool_level": 3,
            "capabilities": {"host.read_file": {"max_per_incident": 5}, "host.cpu": {"max_per_incident": 4}},
            "inspection": {"targets": {"vm-166/host:vm-166": {"files": ["/var/log/myapp/"]}}, **ins}}
    return PolicyEngine(data, yaml.safe_dump(data))


def test_the_engine_checks_the_inspection_policy_after_the_other_rules():
    eng = _engine()
    kw = dict(level=3, safety_class="READ_ONLY_SENSITIVE", target=HOST166, incident_scope={HOST166}, used_in_incident=0)
    assert eng.check(capability="host.read_file", arguments={"path": "/var/log/myapp/a.log"}, **kw).allowed
    d = eng.check(capability="host.read_file", arguments={"path": "/etc/passwd"}, **kw)
    assert not d.allowed and d.rule == "inspection"
    d = eng.check(capability="host.read_file", arguments=None, **kw)        # no arguments: nothing to allow
    assert not d.allowed and d.rule == "inspection"
    with pytest.raises(ValueError, match="arbitrary_exec"):
        _engine(arbitrary_exec=True)


def test_invoke_capability_refuses_and_audits_before_any_executor_call():
    from argus.application.invoke_capability import InvocationContext, InvokeCapability
    from argus.domain.model import Incident

    class PathArgs(BaseModel):
        path: str

    calls = []

    class Spec:
        name, level, safety_class, permission = "host.read_file", 3, "READ_ONLY_SENSITIVE", "read"
        target_kinds = frozenset({"host"})
        args_model = PathArgs

    class Catalogue:
        def spec(self, name):
            return Spec if name == "host.read_file" else None

        def call(self, *a):
            calls.append(a)
            raise AssertionError("the executor must not be called")

    class Inv:
        def target(self, ref):
            return object()

    class Redactor:
        def value(self, v):
            return v, 0

        def text(self, t):
            return t, 0

    class Sink(list):
        def append_evidence(self, rec):
            self.append(rec)

    audit, mem = [], Sink()
    audit_sink = type("A", (), {"append": lambda self, r: audit.append(r)})()
    inc = Incident.model_construct(id="inc_t0019b3a", target=HOST166)
    inv = InvokeCapability(Catalogue(), _engine(), Inv(), mem, audit_sink, Redactor())
    obs, _ = inv(InvocationContext(incident=inc, caller="model", scope={HOST166}), "host.read_file",
                 {"target": str(HOST166), "path": "/etc/shadow"})
    assert obs.status == "refused" and obs.error_category == "forbidden" and not calls
    assert any(a.event == "tool.refused" and a.policy_rule == "inspection" for a in audit)


# --- startup validation and the probe's copy -------------------------------------------------------------------------

def test_inspection_entries_must_be_inventory_targets_under_declared_mounts():
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    ok = _policy()
    assert ok.errors_against_inventory(inv) == []
    unknown = _policy(targets={"vm-166/container:nope": {"service_config": [NGINX_CONF]}})
    assert any("not an inventory target" in e for e in unknown.errors_against_inventory(inv))
    inv2 = json.loads(json.dumps(inv))
    for t in inv2["targets"]:
        if t["ref"] == "vm-166/host:vm-166":
            t["mounts"] = ["/srv/argus-lab-fill"]                              # "/" no longer declared on vm-166
    assert any("declared mount" in e for e in ok.errors_against_inventory(inv2))


def test_build_refuses_to_start_on_an_inspection_error(tmp_path):
    from argus.infrastructure.wiring import Settings, build
    for f in ("inventory.yaml", "signals.yaml", "routing.yaml"):
        if (ROOT / "config" / f).exists():
            (tmp_path / f).write_bytes((ROOT / "config" / f).read_bytes())
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    pol["inspection"]["targets"]["vm-166/container:not-in-inventory"] = {"processes": True}
    (tmp_path / "policy.yaml").write_text(yaml.safe_dump(pol), encoding="utf-8")
    with pytest.raises(SystemExit, match="not an inventory target"):
        build(Settings(config_dir=tmp_path, secrets_dir=tmp_path), require_credentials=False)


def _render():
    spec = importlib.util.spec_from_file_location("render_t0019b3a", ROOT / "ops" / "render_target_config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_each_probe_gets_its_own_hosts_inspection_policy():
    render = _render()
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    for host in ("vm-095", "vm-166"):
        cfg = render.render_host(inv, host)
        ins = cfg["inspection"]
        assert all(ref.startswith(f"{host}/") for ref in ins["targets"])
        assert set(BUILTIN_DENY) <= set(ins["deny"]) and ins["arbitrary_exec"] is False and ins["limits"]
        committed = json.loads((ROOT / "deploy" / "target" / "config" / f"{host}.json").read_text(encoding="utf-8"))
        assert committed == cfg                                                # the committed file is up to date
    assert "vm-166/container:argus-lab-nginx" in render.render_host(inv, "vm-166")["inspection"]["targets"]
