"""LOCAL-CI: `ops/local_ci.py` runs the checks of .github/workflows/ci.yml on a developer's laptop when GitHub Actions
does not run them, and prints one result block bound to the commit it checked (brain/agents/REVIEW_PROTOCOL.md).

The checks themselves are the project's (brain.py, pytest, gitleaks, promtool, npm); these tests cover what the
script decides: a missing tool is SKIPPED (never a pass), any failure makes the whole run FAIL, a test that fails once
and passes alone is reported as flaky, and the result names the exact commit.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("local_ci", ROOT / "ops" / "local_ci.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["local_ci"] = mod                        # dataclasses look the module up while it loads
    spec.loader.exec_module(mod)
    return mod


lci = _load()
SHA = "0123456789abcdef0123456789abcdef01234567"


class FakeRunner:
    """Answers commands by the first matching word; records every call."""

    def __init__(self, answers: dict[str, list[tuple[int, str]]]):
        self.answers, self.calls = answers, []

    def __call__(self, cmd, cwd=None, env=None, timeout=None):
        self.calls.append(list(cmd))
        line = " ".join(map(str, cmd))
        for key, outs in self.answers.items():
            if key in line:
                return outs.pop(0) if len(outs) > 1 else outs[0]
        return 0, ""


def _ci(tmp_path, answers=None, tools=("docker", "npm", "gh")):
    return lci.LocalCI(tmp_path, runner=FakeRunner(answers or {}), which=lambda t: t if t in tools else None)


def test_a_missing_tool_is_skipped_not_passed(tmp_path):
    ci = _ci(tmp_path, tools=())
    r = ci.secrets()
    assert r.status == "skipped" and "docker" in r.detail
    assert lci.overall([r]) == "PASS"                     # skips do not fail the run ...
    assert "skipped: secrets" in lci.report(SHA, [r], pr=7)   # ... but are named in the result


def test_any_failure_fails_the_run(tmp_path):
    ci = _ci(tmp_path, {"brain.py lint": [(1, "LINT FAILED: x")]})
    results = [ci.audit(), ci.lint()]
    assert [r.status for r in results] == ["pass", "fail"]
    assert lci.overall(results) == "FAIL"
    assert "LOCAL CI FAIL 0123456789ab" in lci.report(SHA, results, pr=7)


def test_a_test_that_fails_once_and_passes_alone_is_flaky(tmp_path):
    ci = _ci(tmp_path, {"--tb=short": [(0, "1 passed")],
                        "pytest": [(1, "FAILED tests/test_x.py::test_slow - AssertionError\n1 failed, 9 passed")]})
    r = ci.tests(postgres=False)
    assert r.status == "flaky" and "tests/test_x.py::test_slow" in r.detail
    assert lci.overall([r]) == "PASS"
    assert "flaky" in lci.report(SHA, [r], pr=7)


def test_a_test_that_fails_again_alone_fails(tmp_path):
    ci = _ci(tmp_path, {"--tb=short": [(1, "1 failed")],
                        "pytest": [(1, "FAILED tests/test_x.py::test_bad - AssertionError\n1 failed")]})
    assert ci.tests(postgres=False).status == "fail"


def test_without_docker_postgres_tests_are_reported_as_not_run(tmp_path):
    ci = _ci(tmp_path, {"pytest": [(0, "500 passed, 20 skipped")]}, tools=("npm",))
    r = ci.tests(postgres=True)
    assert r.status == "pass" and "without Postgres" in r.detail


def test_the_report_names_the_commit_and_every_step(tmp_path):
    ci = _ci(tmp_path)
    results = [ci.audit(), ci.lint()]
    text = lci.report(SHA, results, pr=12)
    assert text.splitlines()[0] == "LOCAL CI PASS 0123456789ab (PR #12, commit 0123456789abcdef0123456789abcdef01234567)"
    assert "| audit | pass |" in text and "| lint | pass |" in text


def test_the_tests_row_shows_pytests_summary_and_postgres(tmp_path):
    out = "SKIPPED [1] tests/test_a.py:9: needs Docker\n===== 540 passed, 20 skipped in 612.30s ====="
    ci = _ci(tmp_path, {"docker port": [(0, "127.0.0.1:55001\n")], "pytest": [(0, out)]})
    r = ci.tests(postgres=True)
    assert r.status == "pass" and r.detail == "540 passed, 20 skipped in 612.30s (with Postgres)"


def test_a_failure_without_named_tests_shows_the_exit_code_and_summary(tmp_path):
    out = "SKIPPED [1] tests/test_a.py:9: needs Docker\nFatal Python error: Segmentation fault"
    ci = _ci(tmp_path, {"pytest": [(3221225477, out)]}, tools=())
    r = ci.tests(postgres=False)
    assert r.status == "fail" and r.detail.startswith("pytest exit 3221225477: ")
    assert r.detail.endswith("Fatal Python error: Segmentation fault")


def test_a_known_laptop_failure_is_named_and_does_not_fail_the_run(tmp_path):
    bench = "tests/test_mcp_child.py::test_benchmark_compares_direct_and_mcp_on_the_same_read"
    assert bench in lci.KNOWN_LOCAL
    ci = _ci(tmp_path, {"--tb=short": [(1, "1 failed")],
                        "pytest": [(1, f"FAILED {bench} - AssertionError\n1 failed, 674 passed")]})
    r = ci.tests(postgres=False)
    assert r.status == "known-local" and bench in r.detail
    assert lci.overall([r]) == "PASS" and "known-local" in lci.report(SHA, [r], pr=7)
    other = _ci(tmp_path, {"--tb=short": [(1, "2 failed")],
                           "pytest": [(1, f"FAILED {bench} - x\nFAILED tests/test_y.py::test_z - y\n2 failed")]})
    assert other.tests(postgres=False).status == "fail"            # anything else still fails


def test_every_mode_checks_a_clean_worktree_of_the_commit_never_this_checkout(tmp_path, monkeypatch):
    """#111 review: without --pr/--main the checks ran in this checkout, so gitleaks also scanned its ignored files
    (.venv, node_modules, output.bash). Every mode now checks a temporary worktree of the commit."""
    calls, seen = [], {}

    def git(*args, cwd=None):
        calls.append(args)
        return "" if args[0] == "status" else SHA
    monkeypatch.setattr(lci, "_git", git)
    monkeypatch.setattr(lci, "run", lambda *a, **k: (0, ""))

    class Probe:
        def __init__(self, src):
            seen["src"] = Path(src)

        def all(self, main=False):
            return [lci.Result("audit", "pass")]
    monkeypatch.setattr(lci, "LocalCI", Probe)
    for argv in ([], ["--main"]):
        calls.clear()
        assert lci.main(argv) == 0
        add = [c for c in calls if c[0] == "worktree"]
        assert add and add[0][-1] == SHA, argv
        assert seen["src"] != lci.REPO and "argus-localci-" in str(seen["src"]), argv
