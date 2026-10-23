"""T-0019 batch 3b: the host-probe verbs that read files, service configuration, the journal and process details, under
the inspection policy of 3a (ARCHITECTURE §4.6, §4.7, §12.2 Level 3).

Each verb is checked twice: by the agent's policy engine before execution (3a) and by the probe against its rendered
copy of the same policy (here). The probe's path check is its own small function (the probe image carries only the
standard library), so a parity test runs both on the same paths. A path is read only when its real location under
/rootfs is exactly the requested one (no symlink anywhere), it is a regular file, and within the line and byte
bounds. The journal comes from rsyslog's text copy (/var/log/syslog), filtered by the unit's program (decided
2026-10-12, `conantkd`). Process details never include `cmdline` or `environ`. Only `host.service_config` is offered
to a class (`nginx_upstream_failure`: its `proxy_read_timeout`); the other three wait until a case needs them.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
import yaml

from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES
from argus.domain.model import TargetRef
from argus.policy.inspection import InspectionPolicy

ROOT = Path(__file__).resolve().parents[1]
SPECS = {s.name: s for s in build_catalog()}
HOST = "vm-166/host:vm-166"
NGINX = "vm-166/container:argus-lab-nginx"
CONF = "/opt/argus-v18/app/deploy/lab/nginx/default.conf"
NGINX_CONF_TEXT = (ROOT / "deploy" / "lab" / "nginx" / "default.conf").read_text(encoding="utf-8")


def _inspection():
    return {"targets": {HOST: {"files": ["/var/log/myapp/"], "processes": True,
                               "journal": {"units": ["docker.service", "containerd.service"], "max_lines": 200}},
                        NGINX: {"service_config": [CONF]}},
            "deny": ["*token*"], "limits": {"max_lines": 500, "max_bytes": 65536}, "arbitrary_exec": False}


@pytest.fixture
def probe(tmp_path, monkeypatch):
    rootfs, proc = tmp_path / "rootfs", tmp_path / "proc"
    (rootfs / "var" / "log" / "myapp").mkdir(parents=True)
    (rootfs / "var" / "log" / "myapp" / "app.log").write_text("".join(f"line {i}\n" for i in range(1, 301)), encoding="utf-8")
    (rootfs / "var" / "log" / "myapp" / "api_token.txt").write_text("s3cr3t\n", encoding="utf-8")
    (rootfs / "opt" / "argus-v18" / "app" / "deploy" / "lab" / "nginx").mkdir(parents=True)
    (rootfs / CONF.lstrip("/")).write_text(NGINX_CONF_TEXT, encoding="utf-8")
    (rootfs / "var" / "log" / "syslog").write_text(
        "Oct 12 20:40:01 argus-vm166 systemd[1]: Started Session 1.\n"
        "Oct 12 20:41:02 argus-vm166 dockerd[812]: level=error msg=\"restart canceled\" container=c0ffee\n"
        "Oct 12 20:41:03 argus-vm166 containerd[640]: level=info msg=\"shim disconnected\" id=c0ffee\n"
        "Oct 12 20:41:04 argus-vm166 sshd[999]: Accepted publickey for ubuntu\n"
        "Oct 12 20:41:05 argus-vm166 dockerd[812]: level=warning msg=\"health check failed\" container=c0ffee\n",
        encoding="utf-8")
    p = proc / "4242"
    p.mkdir(parents=True)
    (p / "status").write_text("Name:\tpython\nState:\tS (sleeping)\nPPid:\t4200\nThreads:\t3\nVmRSS:\t  41200 kB\n"
                              "VmHWM:\t  60000 kB\nvoluntary_ctxt_switches:\t10\nnonvoluntary_ctxt_switches:\t2\n",
                              encoding="utf-8")
    (p / "limits").write_text("Limit                     Soft Limit           Hard Limit           Units\n"
                              "Max open files            1024                 4096                 files\n"
                              "Max processes             63429                63429                processes\n",
                              encoding="utf-8")
    (p / "cgroup").write_text("0::/system.slice/docker-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef.scope\n", encoding="utf-8")
    (p / "fd").mkdir()
    for i in range(5):
        (p / "fd" / str(i)).write_text("", encoding="utf-8")
    (p / "cmdline").write_text("python\0--password=hunter2\0", encoding="utf-8")
    (p / "environ").write_text("SECRET=x\0", encoding="utf-8")
    cfg = tmp_path / "target.json"
    cfg.write_text(json.dumps({"host": "vm-166", "containers": ["argus-lab-nginx"], "mounts": ["/"],
                               "inspection": InspectionPolicy.from_data(_inspection()).for_host("vm-166")}),
                   encoding="utf-8")
    monkeypatch.setenv("ROLE", "exporter")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    monkeypatch.setenv("TA_ROOTFS", str(rootfs))
    monkeypatch.setenv("TA_PROC", str(proc))
    spec = importlib.util.spec_from_file_location("ta_service_3b", ROOT / "services" / "target" / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOTFS_DIR = rootfs
    return mod


def q(**kw):
    return {k: [str(v)] for k, v in kw.items()}


# --- read_file ----------------------------------------------------------------------------------------------------

def test_read_file_reads_the_last_lines_of_an_allowed_file(probe):
    d = probe.host_probe(["read_file"], q(target=HOST, path="/var/log/myapp/app.log", lines=3))
    assert d["lines"] == ["line 298", "line 299", "line 300"] and d["path"] == "/var/log/myapp/app.log"
    assert d["truncated"] is True and d["lines_returned"] == 3


@pytest.mark.parametrize("path,code", [("/etc/passwd", 403), ("/var/log/myapp/api_token.txt", 403),
                                       ("/var/log/myapp/../myapp/app.log", 403), ("/var/log/myapp/missing.log", 404),
                                       ("/var/log/myapp/", 403)])
def test_read_file_refuses_what_the_policy_or_the_filesystem_does_not_allow(probe, path, code):
    with pytest.raises(probe.Err) as e:
        probe.host_probe(["read_file"], q(target=HOST, path=path, lines=10))
    assert e.value.code == code


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_read_file_never_follows_a_symlink(probe):
    link = probe.ROOTFS_DIR / "var" / "log" / "myapp" / "passwd.log"
    os.symlink("/etc/passwd", link)
    with pytest.raises(probe.Err) as e:
        probe.host_probe(["read_file"], q(target=HOST, path="/var/log/myapp/passwd.log", lines=10))
    assert e.value.code == 403


def test_read_file_refuses_a_target_without_an_entry_and_a_line_count_above_the_limit(probe):
    with pytest.raises(probe.Err) as e:
        probe.host_probe(["read_file"], q(target="vm-166/host:other", path="/var/log/myapp/app.log", lines=3))
    assert e.value.code == 403
    with pytest.raises(probe.Err) as e:
        probe.host_probe(["read_file"], q(target=HOST, path="/var/log/myapp/app.log", lines=501))
    assert e.value.code == 400


def test_the_probe_and_the_agent_decide_paths_the_same_way(probe):
    pol = InspectionPolicy.from_data(_inspection())
    host = TargetRef.parse(HOST)
    for path in ["/var/log/myapp/app.log", "/var/log/myapp/x/y.log", "/var/log/myapp", "/var/log/myapp/.env",
                 "/var/log/myapp/k.PEM", "/var/log/myapp/db_password", "/var/log/myapp/../../etc/passwd",
                 "/var/log/myapp/./a", "//var/log/myapp/a", "/run/secrets/x", "/opt/argus-v18/secrets/t", "/root/a",
                 "relative", "/var/log/myapp/a\x00b"]:
        agent = pol.allows(host, "host.read_file", {"path": path}).allowed
        assert probe.inspection_allows(HOST, "files", path) == agent, path


# --- service_config ------------------------------------------------------------------------------------------------

def test_service_config_returns_the_allowed_files_of_a_target(probe):
    d = probe.host_probe(["service_config"], q(target=NGINX))
    assert [f["path"] for f in d["files"]] == [CONF]
    assert "proxy_read_timeout 2s;" in d["files"][0]["text"] and d["files"][0]["truncated"] is False
    d = probe.host_probe(["service_config"], q(target=NGINX, path=CONF))
    assert len(d["files"]) == 1
    with pytest.raises(probe.Err):
        probe.host_probe(["service_config"], q(target=NGINX, path="/etc/nginx/nginx.conf"))
    with pytest.raises(probe.Err):
        probe.host_probe(["service_config"], q(target=HOST))              # no service_config entry for the host


# --- journal -------------------------------------------------------------------------------------------------------

def test_journal_returns_only_the_units_program_lines(probe):
    d = probe.host_probe(["journal"], q(target=HOST, unit="docker.service", lines=50))
    assert d["source"] == "syslog" and d["program"] == "dockerd"
    assert len(d["lines"]) == 2 and all("dockerd[812]" in ln for ln in d["lines"])
    d = probe.host_probe(["journal"], q(target=HOST, unit="containerd.service", lines=50))
    assert len(d["lines"]) == 1 and "shim disconnected" in d["lines"][0]
    for unit, lines, code in (("ssh.service", 10, 403), ("docker.service", 201, 400)):
        with pytest.raises(probe.Err) as e:
            probe.host_probe(["journal"], q(target=HOST, unit=unit, lines=lines))
        assert e.value.code == code


def test_journal_without_syslog_is_unavailable_not_empty(probe):
    (probe.ROOTFS_DIR / "var" / "log" / "syslog").unlink()
    d = probe.host_probe(["journal"], q(target=HOST, unit="docker.service", lines=50))
    assert d["source"] == "unavailable" and d["lines"] is None


# --- process_details ------------------------------------------------------------------------------------------------

def test_process_details_reads_status_limits_and_fds_never_cmdline_or_environ(probe):
    d = probe.host_probe(["process_details"], q(target=HOST, pid=4242))
    assert d["name"] == "python" and d["state"] == "S" and d["threads"] == 3 and d["rss_mib"] == 40.2
    assert d["open_files"] == 5 and d["limits"]["max_open_files"] == [1024, 4096]
    assert d["container_id"] == "0123456789ab"
    text = json.dumps(d)
    assert "hunter2" not in text and "SECRET" not in text and "cmdline" not in text and "environ" not in text
    with pytest.raises(probe.Err) as e:
        probe.host_probe(["process_details"], q(target=HOST, pid=99999))
    assert e.value.code == 404
    with pytest.raises(probe.Err) as e:
        probe.host_probe(["process_details"], q(target=NGINX, pid=4242))     # processes not allowed there
    assert e.value.code == 403


# --- capabilities, policy and offering ----------------------------------------------------------------------------

def test_the_four_capabilities_are_level_3_sensitive_host_probe_reads():
    names = {"host.read_file": "inspect_approved_file", "host.service_config": "inspect_service_config",
             "host.journal": "get_journal_logs", "host.process_details": "inspect_process_details"}
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    for name, model_name in names.items():
        s = SPECS[name]
        assert (s.model_name, s.level, s.safety_class, s.executor) == (model_name, 3, "READ_ONLY_SENSITIVE", "host_probe")
        assert pol["capabilities"][name]["max_per_incident"] >= 1, name
    offered = {name: [c.name for c in CLASSES if SPECS[name].tags & c.tool_tags] for name in names}
    assert offered == {"host.read_file": [], "host.service_config": ["nginx_upstream_failure"],
                       "host.journal": [], "host.process_details": []}


class _Client:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.answer


def test_service_config_shows_the_files_to_the_model():
    s = SPECS["host.service_config"]
    c = _Client({"files": [{"path": CONF, "text": NGINX_CONF_TEXT, "truncated": False}], "collected_at": None})
    r = s.impl(s.args_model(), TargetRef.parse(NGINX), None, c)
    assert c.calls == [("/service_config", {"target": NGINX})]
    assert "proxy_read_timeout 2s;" in r.model_text and CONF in r.model_text


def test_journal_and_process_details_texts():
    j = SPECS["host.journal"]
    c = _Client({"source": "syslog", "program": "dockerd", "lines": ["Oct 12 dockerd[812]: x"], "collected_at": None})
    r = j.impl(j.args_model(unit="docker.service"), TargetRef.parse(HOST), None, c)
    assert c.calls == [("/journal", {"target": HOST, "unit": "docker.service", "lines": 50})] and "dockerd[812]" in r.model_text
    r = j.impl(j.args_model(unit="docker.service"), TargetRef.parse(HOST), None,
               _Client({"source": "unavailable", "lines": None, "collected_at": None}))
    assert "unknown" in r.model_text
    p = SPECS["host.process_details"]
    c = _Client({"pid": 4242, "name": "python", "state": "S", "threads": 3, "rss_mib": 40.2, "hwm_mib": 58.6,
                 "open_files": 5, "limits": {"max_open_files": [1024, 4096]}, "container_id": "0123456789ab",
                 "collected_at": None})
    r = p.impl(p.args_model(pid=4242), TargetRef.parse(HOST), None, c)
    assert "pid 4242 python" in r.model_text and "open files 5 / 1024" in r.model_text


def test_service_config_needs_no_path_in_the_agents_policy_either():
    pol = InspectionPolicy.from_data(_inspection())
    assert pol.allows(TargetRef.parse(NGINX), "host.service_config", {"path": None}).allowed
    assert not pol.allows(TargetRef.parse(HOST), "host.service_config", {"path": None}).allowed


# --- evaluation cases ------------------------------------------------------------------------------------------------

def test_the_nginx_cases_answer_service_config_with_the_lab_file():
    seen = 0
    for p in sorted((ROOT / "tests" / "eval" / "cases").glob("nginx-*.yaml")):
        case = yaml.safe_load(p.read_text(encoding="utf-8"))
        ans = case["fixtures"]["host_probe"][f"/service_config?target={NGINX}"]
        assert ans["files"][0]["path"] == CONF and ans["files"][0]["text"] == NGINX_CONF_TEXT, p.name
        seen += 1
    assert seen == 6


# --- the deny floor (#98 / #103 review, `juanbetancurm`): closed before any path is added to `files` ----------------

FLOOR_DENIED = ["/proc/1/environ", "/proc/self/mem", "/var/lib/docker/containers/c0ffee/config.v2.json",
                "/home/ubuntu/.ssh/config", "/home/ubuntu/.ssh/authorized_keys", "/root/.ssh/known_hosts",
                "/home/ubuntu/keys/id_ed25519", "/home/ubuntu/id_rsa.pub", "/srv/app/prod.env", "/srv/app/.env",
                "/srv/app/.ENV", "/srv/tokens/readme.txt", "/srv/Passwords/list.txt", "/srv/app/db_password",
                "/srv/app/api_token.txt", "/etc/shadow", "/etc/shadow-", "/etc/gshadow", "/etc/gshadow-",
                "/etc/sudoers", "/etc/sudoers.d/90-cloud-init-users", "/run/secrets/db", "/srv/k.PEM"]
FLOOR_ALLOWED = ["/var/log/syslog", "/etc/hostname", "/etc/nginx/nginx.conf", "/srv/app/environment.md",
                 "/srv/app/app.log"]


def _allow_everything(probe):
    """A policy whose allowlist is the whole filesystem and whose data denies nothing: only the floor is left."""
    data = {"targets": {HOST: {"files": ["/"]}}, "deny": [], "limits": {"max_lines": 500, "max_bytes": 65536},
            "arbitrary_exec": False}
    pol = InspectionPolicy.from_data(data)
    probe.CONFIG["inspection"] = pol.for_host("vm-166")
    return pol


@pytest.mark.parametrize("path", FLOOR_DENIED)
def test_the_deny_floor_refuses_credentials_and_kernel_state_whatever_the_allowlist(probe, path):
    pol = _allow_everything(probe)
    assert pol.allows(TargetRef.parse(HOST), "host.read_file", {"path": path}).allowed is False, path
    assert probe.inspection_allows(HOST, "files", path) is False, path


@pytest.mark.parametrize("path", FLOOR_ALLOWED)
def test_the_deny_floor_leaves_ordinary_files_alone(probe, path):
    pol = _allow_everything(probe)
    assert pol.allows(TargetRef.parse(HOST), "host.read_file", {"path": path}).allowed is True, path
    assert probe.inspection_allows(HOST, "files", path) is True, path


def test_a_name_pattern_matches_every_component_of_the_path_not_only_the_file_name():
    from argus.policy.inspection import _denied
    assert _denied("/srv/tokens/readme.txt", ("*token*",)) == "*token*"          # a directory, not the file
    assert _denied("/home/u/.ssh/config", (".ssh",)) == ".ssh"
    assert _denied("/srv/app/readme.txt", ("*token*", ".ssh")) is None


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_symlink_swapped_in_after_the_walk_is_not_followed(probe, monkeypatch):
    """#103 review: the walk checks each component, then the file is opened with O_NOFOLLOW, so a link put in its
    place between the check and the open is refused (ELOOP), never read."""
    log = probe.ROOTFS_DIR / "var" / "log" / "myapp" / "swap.log"
    os.symlink("/etc/passwd", log)
    monkeypatch.setattr(probe.os.path, "islink", lambda p: False)       # the walk saw a regular file
    monkeypatch.setattr(probe.os, "lstat", lambda p: os.stat(probe.ROOTFS_DIR / "var" / "log" / "myapp" / "app.log"))
    with pytest.raises(probe.Err) as e:
        probe.host_probe(["read_file"], q(target=HOST, path="/var/log/myapp/swap.log", lines=10))
    assert e.value.code == 403


def test_the_file_is_opened_without_following_links_and_checked_on_the_open_descriptor(probe, monkeypatch):
    flags = []
    real_open = probe.os.open

    def spy(path, flag, *a, **kw):
        flags.append(flag)
        return real_open(path, flag, *a, **kw)
    monkeypatch.setattr(probe.os, "open", spy)
    d = probe.host_probe(["read_file"], q(target=HOST, path="/var/log/myapp/app.log", lines=2))
    assert d["lines"] == ["line 299", "line 300"]
    assert flags and all(f & probe.O_NOFOLLOW == probe.O_NOFOLLOW for f in flags)
    assert probe.O_NOFOLLOW == getattr(os, "O_NOFOLLOW", 0)
    d = probe.host_probe(["service_config"], q(target=NGINX))
    assert "proxy_read_timeout" in d["files"][0]["text"] and len(flags) == 2


def test_the_probe_applies_the_same_floor_even_if_its_rendered_copy_leaves_it_out(probe):
    from argus.policy.inspection import BUILTIN_DENY
    assert probe.INSPECT_FLOOR == BUILTIN_DENY
    probe.CONFIG["inspection"] = {"targets": {HOST: {"files": ["/"]}}, "deny": [], "limits": {}}   # a stale copy
    assert probe.inspection_allows(HOST, "files", "/home/ubuntu/.ssh/id_ed25519") is False
    assert probe.inspection_allows(HOST, "files", "/var/log/syslog") is True


# --- the Argus side of read_file (the gateway tests above never ran it) -------------------------------------------------
@pytest.mark.parametrize("more_before", [True, False])
def test_the_read_file_capability_turns_the_answer_into_a_result(more_before):
    from argus.capabilities.catalog import FileArgs, host_read_file

    class Gateway:
        def get(self, path, params):
            return {"lines": ["a", "b"], "lines_returned": 2, "truncated": more_before,
                    "collected_at": "2026-10-21T00:00:00+00:00"}

    res = host_read_file(FileArgs(path="/var/log/myapp/app.log"), TargetRef.parse("vm-166/host:vm-166"), None,
                         Gateway())
    assert res.status == "ok" and res.partial is more_before and res.coverage == "last 2 line(s) of /var/log/myapp/app.log"
    assert res.model_text.endswith("a" + chr(10) + "b") and ("(more before)" in res.model_text) is more_before
