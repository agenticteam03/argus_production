import importlib.util
import os
import shutil
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_api(monkeypatch, enabled="1"):
    monkeypatch.setenv("FAULT_ENABLE", enabled)
    monkeypatch.setenv("CACHE_HOST", "none")
    source = ROOT / "deploy" / "lab" / "workloads" / "api.py"
    spec = importlib.util.spec_from_file_location("s1_lab_api", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api_server(monkeypatch):
    module = _load_api(monkeypatch)
    server = module.make_server(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    yield base
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_fault_burns_cpu_asynchronously_and_health_stays_available(api_server):
    cpu_before = time.process_time()

    with urllib.request.urlopen(api_server + "/fault/cpu?s=2", timeout=3) as response:
        assert response.status == 202

    with urllib.request.urlopen(api_server + "/health", timeout=3) as response:
        assert response.status == 200

    time.sleep(0.25)
    assert time.process_time() - cpu_before > 0.05


def test_fault_route_is_hidden_when_disabled(monkeypatch):
    module = _load_api(monkeypatch, enabled="0")
    server = module.make_server(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/fault/cpu?s=1", timeout=3)
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _bash():
    candidates = [shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            result = subprocess.run([candidate, "-c", "exit 0"], capture_output=True, check=False, timeout=5)
            if result.returncode == 0:
                return candidate
    pytest.skip("a working POSIX shell is required")


def _fake_tools(tmp_path, hostname):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for command, contents in {
        "hostname": f"#!/bin/sh\nprintf '%s\\n' '{hostname}'\n",
        "docker": "#!/bin/sh\nprintf '%s\\n' \"$*\" >> docker.calls\n",
    }.items():
        path = bindir / command
        path.write_text(contents, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    return env


def _run_with_shell_shims(bash, script_path, args, tmp_path, hostname):
    shims = (
        'hostname() { printf "%s\\n" "$S1_TEST_HOST"; }; '
        'docker() { printf "%s\\n" "$*" >> docker.calls; }; '
        'source "$1" "${@:2}"'
    )
    env = os.environ.copy()
    env["S1_TEST_HOST"] = hostname
    return subprocess.run([bash, "-c", shims, "s1-test", str(script_path), *args], cwd=tmp_path,
                          env=env, capture_output=True, text=True, check=False, timeout=5)


def test_scripts_have_valid_posix_shell_syntax():
    bash = _bash()
    for name in ("s1-inject.sh", "s1-reset.sh"):
        result = subprocess.run([bash, "-n", str(ROOT / "deploy" / "lab" / "demo" / name)],
                                capture_output=True, text=True, check=False, timeout=5)
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", ["s1-inject.sh", "s1-reset.sh"])
def test_scripts_refuse_non_lab_names_without_calling_docker(tmp_path, script):
    bash = _bash()
    script_path = ROOT / "deploy" / "lab" / "demo" / script
    assert script_path.is_file()
    result = subprocess.run([bash, str(script_path), "not-a-lab-container"], cwd=tmp_path,
                            env=_fake_tools(tmp_path, "vm-166"), capture_output=True, text=True,
                            check=False, timeout=5)

    assert result.returncode != 0
    assert not (tmp_path / "docker.calls").exists()


@pytest.mark.parametrize("script", ["s1-inject.sh", "s1-reset.sh"])
def test_scripts_refuse_vm095_without_calling_docker(tmp_path, script):
    bash = _bash()
    script_path = ROOT / "deploy" / "lab" / "demo" / script
    assert script_path.is_file()
    result = _run_with_shell_shims(bash, script_path, ["argus-lab-cache"], tmp_path, "vm-095")

    assert result.returncode != 0
    assert not (tmp_path / "docker.calls").exists()


@pytest.mark.parametrize(
    "script,args,expected",
    [
        ("s1-inject.sh", ["argus-lab-cache", "cpu", "1"], "stop argus-lab-cache"),
        ("s1-reset.sh", ["argus-lab-cache"], "start argus-lab-cache"),
    ],
)
def test_valid_scripts_can_be_repeated_with_lab_container(tmp_path, script, args, expected):
    bash = _bash()
    script_path = ROOT / "deploy" / "lab" / "demo" / script

    for _ in range(2):
        result = _run_with_shell_shims(bash, script_path, args, tmp_path, "vm-166")
        assert result.returncode == 0, result.stderr

    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8").splitlines()
    assert sum(call.startswith(expected) for call in calls) == 2
