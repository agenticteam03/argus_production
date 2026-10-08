"""T-0021 step 2: the tools process is a real child of the worker, over stdio (ARCHITECTURE §12.5, §12.6).

The child builds its own dispatcher from the config and the secrets folder (it, not the worker, reads the executor
tokens), answers over stdin/stdout, and is restarted after it dies. `ARGUS_TOOL_CATALOGUE=mcp|direct` selects it;
the investigation is the same either way.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from argus.domain.model import TargetRef
from test_core import ROOT, FakeMetrics, incident, make_app  # noqa: F401  (make_app = fixture)

API = TargetRef.parse("vm-166/container:argus-lab-api")
TOKEN = "tok-docker-166"


class _Gateway(BaseHTTPRequestHandler):
    seen: list[str] = []

    def do_GET(self):  # noqa: N802
        _Gateway.seen.append(self.headers.get("Authorization", ""))
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.send_response(401), self.end_headers()
            return
        body = json.dumps({"id": "bbb222", "state": "running", "health": "healthy", "restart_count": 0,
                           "oom_killed": False, "exit_code": 0, "networks": ["argus-lab-app"]}).encode()
        self.send_response(200), self.send_header("Content-Type", "application/json"), self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def child_env(tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Gateway)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    cfg = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg)
    inv = yaml.safe_load((cfg / "inventory.yaml").read_text(encoding="utf-8"))
    for h in inv["hosts"].values():
        h["executors"] = {k: url for k in h["executors"]}
    (cfg / "inventory.yaml").write_text(yaml.safe_dump(inv), encoding="utf-8")
    sec = tmp_path / "secrets"
    for host, h in inv["hosts"].items():
        (sec / host).mkdir(parents=True)
        for ex in h["executors"]:
            (sec / host / f"{ex}_token").write_text(TOKEN if (host, ex) == ("vm-166", "docker_read") else "other")
    _Gateway.seen = []
    yield {"ARGUS_CONFIG_DIR": str(cfg), "ARGUS_SECRETS_DIR": str(sec), "PYTHONPATH": str(ROOT)}
    srv.shutdown()


def _child_pids() -> list[int]:
    pids = []
    for p in Path("/proc").glob("[0-9]*"):
        try:
            if b"argus.tooling.mcp.tools_server" in (p / "cmdline").read_bytes():
                pids.append(int(p.name))
        except OSError:
            pass
    return pids


def test_the_child_process_reads_with_its_own_token(child_env):
    from argus.tooling.mcp.client import child_client
    client = child_client(child_env)
    try:
        obs = client.call("container.status", str(API), {})
        assert obs.status == "ok" and obs.host == "vm-166" and "running" in obs.model_text
        assert _Gateway.seen == [f"Bearer {TOKEN}"]                    # the child read the token from its secrets
        assert client.list_names() and "knowledge.runbook" not in client.list_names()
    finally:
        client.close()


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="needs /proc to find the child (Linux, Docker)")
def test_a_killed_child_gives_an_error_then_a_new_child_answers(child_env):
    from argus.capabilities.catalog import build_catalog
    from argus.tooling.mcp.client import child_client
    from argus.tooling.providers import McpCatalogue
    client = child_client(child_env)
    cat = McpCatalogue(build_catalog(), None, client)
    spec = next(s for s in build_catalog() if s.name == "container.status")
    try:
        assert cat.call(spec, spec.args_model(), API).status == "ok"
        for pid in _child_pids():
            os.kill(pid, signal.SIGKILL)
        dead = cat.call(spec, spec.args_model(), API)
        assert dead.status == "error" and dead.error_category == "upstream_error"
        assert cat.call(spec, spec.args_model(), API).status == "ok"      # a new child was started
    finally:
        client.close()


def test_the_tool_catalogue_setting_selects_the_provider(make_app, monkeypatch):
    from argus.tooling.dispatch import DirectProvider
    from argus.tooling.providers import McpCatalogue
    assert type(make_app().catalogue) is DirectProvider                   # default: direct (until step 5)
    monkeypatch.setenv("ARGUS_TOOL_CATALOGUE", "mcp")
    assert isinstance(make_app().catalogue, McpCatalogue)                 # built lazily: no child started yet
    monkeypatch.setenv("ARGUS_TOOL_CATALOGUE", "bogus")
    with pytest.raises(SystemExit):
        make_app()


def test_an_investigation_is_the_same_through_mcp(make_app, monkeypatch):
    from argus.tooling.mcp.client import McpToolsClient
    from argus.tooling.mcp.tools_server import build_server
    metrics = FakeMetrics({"vm-095/container:argus-lab-worker": {"restarts_10m": 0}})
    direct = make_app(metrics=metrics)
    monkeypatch.setenv("ARGUS_TOOL_CATALOGUE", "mcp")
    viamcp = make_app(metrics=metrics)
    d = direct.catalogue
    viamcp.catalogue.tools = McpToolsClient(build_server(d.list(), d.dispatcher, direct.inventory))
    try:
        a = direct.runner.run(incident(direct, "vm-095/container:argus-lab-worker").id)
        b = viamcp.runner.run(incident(viamcp, "vm-095/container:argus-lab-worker").id)
        assert (b.status, b.outcome) == (a.status, a.outcome)
        reads = lambda app, i: [(e.capability, e.status) for e in app.store.list_evidence(i)  # noqa: E731
                                if e.kind == "observation"]
        assert reads(viamcp, b.id) == reads(direct, a.id) and reads(direct, a.id)
        assert viamcp.catalogue.tools.calls > 0
    finally:
        viamcp.catalogue.tools.close()
