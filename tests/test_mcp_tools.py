"""T-0021 step 1: target-side reads are served by an MCP tools server (ARCHITECTURE §12.5, §12.6).

The server publishes only the `runs_in="tools_child"` capabilities, refuses anything else, and delegates to the same
dispatcher as the direct provider, so an observation read through MCP equals the direct one. In-worker capabilities
(`knowledge.runbook`) never cross MCP. These tests use the in-memory transport; step 2 runs the real child process.
"""
from __future__ import annotations

import pytest

from argus.domain.model import TargetRef
from test_core import make_app  # noqa: F401  (make_app = fixture)

API = TargetRef.parse("vm-166/container:argus-lab-api")
VOLATILE = {"observation_id", "collected_at", "duration_ms"}


@pytest.fixture()
def parts(make_app):
    from argus.tooling.mcp.client import McpToolsClient
    from argus.tooling.mcp.tools_server import build_server
    from argus.tooling.providers import McpCatalogue
    app = make_app()
    direct = app.catalogue
    client = McpToolsClient(build_server(direct.list(), direct.dispatcher, app.inventory))
    yield direct, McpCatalogue(direct.list(), direct.dispatcher, client), client
    client.close()


def test_server_publishes_only_the_tools_child_capabilities(parts):
    direct, _, client = parts
    expected = {s.name for s in direct.list() if s.runs_in == "tools_child"}
    assert client.list_names() == expected
    assert "knowledge.runbook" not in expected and "container.status" in expected


def test_a_read_through_mcp_equals_the_direct_read(parts):
    direct, mcp, _ = parts
    for name in ("container.status", "container.logs", "database.health"):
        spec = direct.spec(name)
        target = TargetRef.parse("vm-166/container:argus-lab-db") if name == "database.health" else API
        a = direct.call(spec, spec.args_model(), target).model_dump(exclude=VOLATILE)
        b = mcp.call(spec, spec.args_model(), target).model_dump(exclude=VOLATILE)
        assert b == a and b["host"] == "vm-166"


def test_server_refuses_an_unpublished_capability(parts):
    _, _, client = parts
    for name in ("knowledge.runbook", "container.restart", "no.such"):
        obs = client.call(name, str(API), {})
        assert obs.status == "refused" and obs.error_category == "forbidden", name


def test_server_refuses_invalid_arguments(parts):
    _, _, client = parts
    obs = client.call("network.http_probe", str(API), {})                     # `url` is required
    assert obs.status == "refused" and obs.error_category == "invalid_args"
    obs = client.call("container.logs", str(API), {"tail": 10_000})           # above the limit (200)
    assert obs.status == "refused" and obs.error_category == "invalid_args"


def test_server_refuses_a_target_outside_the_deployment_scope(parts):
    _, _, client = parts
    for target in ("vm-166/container:nginx", "vm-999/container:argus-lab-api", "not a target"):
        obs = client.call("container.status", target, {})
        assert obs.status == "refused" and obs.error_category in ("out_of_scope", "invalid_args"), target


def test_in_worker_capability_never_crosses_mcp(parts):
    direct, mcp, client = parts
    before = client.calls
    spec = direct.spec("knowledge.runbook")
    obs = mcp.call(spec, spec.args_model(runbook_id="RB-009", query="network"), API)
    assert obs.status == "ok" and "RB-009" in obs.model_text
    assert client.calls == before


def test_a_dead_tools_server_gives_an_error_observation_not_a_crash(parts):
    direct, mcp, client = parts
    client.close()
    spec = direct.spec("container.status")
    obs = mcp.call(spec, spec.args_model(), API)
    assert obs.status == "error" and obs.error_category == "upstream_error"


def test_only_tooling_mcp_imports_the_mcp_sdk():
    """Rule 10 (ARCHITECTURE §2.3): `tooling/mcp/` is the only location of the MCP SDK."""
    from test_core import ROOT, _imports
    sdk = lambda m: m == "mcp" or m.startswith("mcp.") or m.startswith("mcp_types")  # noqa: E731
    offenders = [str(f.relative_to(ROOT)) for f in (ROOT / "argus").rglob("*.py")
                 if any(sdk(m) for m in _imports(f)) and "tooling/mcp" not in f.as_posix()]
    assert offenders == []
