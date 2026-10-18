"""Local CI (LOCAL-CI): the checks of .github/workflows/ci.yml, run on a developer's laptop when GitHub Actions does not
run them (a run "not started", or Actions turned off). See brain/agents/REVIEW_PROTOCOL.md, "When CI does not run".

    python ops/local_ci.py --pr <n> [--post]     the PR's last push, checked out in a clean temporary worktree
    python ops/local_ci.py --main                origin/main, plus `brain.py verify-main` (the main-guard job)
    python ops/local_ci.py                       this checkout's HEAD (the working tree must be clean)

Steps, as in CI: Brain audit and lint; the secret scan (gitleaks in Docker, the files of the commit; CI also scans
the history); the full pytest suite against a throwaway Postgres in Docker (as policies/TDD.md); the OP-005 PromQL
cases (promtool in Docker); the frontend (npm: lint, unit tests, build, Playwright). A missing tool makes its step
SKIPPED, never a pass, and the result says so. A pytest failure is run again alone once: passing alone it is reported "flaky", failing
again it fails. The last line block is the result to paste into the PR (or `--post` comments it with gh), bound to
the exact commit that was checked. Run it from the repository's virtual environment (`pip install -e ".[test]"`).
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PG_IMAGE = "postgres:16-alpine"                       # the CI service image
PROM_IMAGE = "prom/prometheus:v3.5.0"                 # the CI promtool image
GITLEAKS_IMAGE = "ghcr.io/gitleaks/gitleaks:v8.21.2"  # the CI gitleaks version
# Tests that fail on a laptop for a reason of the laptop, not of the code, and pass on CI's Linux runner. Reported by
# name as `known-local`, never hidden; any other failure fails the run. Adding a line here needs a reviewer's approval.
KNOWN_LOCAL = {
    "tests/test_mcp_child.py::test_benchmark_compares_direct_and_mcp_on_the_same_read":
        "a timing budget (p95 overhead of the tools process < 100 ms) measured on the laptop; it holds on CI's runner",
}


@dataclass
class Result:
    name: str
    status: str                                       # pass | fail | skipped | flaky | known-local
    detail: str = ""


def run(cmd, cwd=None, env=None, timeout=None) -> tuple[int, str]:
    """One command; its exit code and combined output (never raises for a non-zero exit)."""
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, timeout=timeout, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except FileNotFoundError as e:
        return 127, str(e)
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout} s"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _summary(out: str) -> str:
    """pytest's own summary line ("540 passed, 20 skipped in 612.3s"), not the last skip reason."""
    rows = [ln.strip("= ").strip() for ln in out.splitlines() if re.search(r"\d+ (passed|failed|error)", ln)]
    return rows[-1] if rows else _tail(out, 1)


def _tail(out: str, n: int = 3) -> str:
    return " / ".join(line.strip() for line in out.strip().splitlines()[-n:] if line.strip())


class LocalCI:
    def __init__(self, src: Path, runner=run, which=shutil.which, python: str = sys.executable):
        self.src, self.run, self.which, self.py = Path(src), runner, which, python
        self.env = {**os.environ, "PYTHONPATH": str(self.src)}   # this checkout's `argus`, not the editable install

    def _brain(self, name: str, *args: str) -> Result:
        code, out = self.run([self.py, "brain/tools/brain.py", *args], cwd=self.src, env=self.env, timeout=600)
        return Result(name, "pass" if code == 0 else "fail", _tail(out, 1 if code == 0 else 5))

    def audit(self) -> Result:
        return self._brain("audit", "audit")

    def lint(self) -> Result:
        return self._brain("lint", "lint")

    def secrets(self) -> Result:
        if not self.which("docker"):
            return Result("secrets", "skipped", "docker not found (gitleaks runs in Docker)")
        code, out = self.run(["docker", "run", "--rm", "--mount", f"type=bind,source={self.src},target=/repo,readonly",
                              GITLEAKS_IMAGE, "detect", "--source", "/repo", "--no-git", "--no-banner", "--redact"],
                             timeout=600)
        return Result("secrets", "pass" if code == 0 else "fail",
                      "gitleaks: no leaks (files of the commit)" if code == 0 else _tail(out, 5))

    def tests(self, postgres: bool = True) -> Result:
        env, note, pg = dict(self.env), "", None
        if postgres and self.which("docker"):
            pg, dsn = self._postgres()
            if dsn:
                env["ARGUS_TEST_PG_OWNER_DSN"] = dsn
                note = " (with Postgres)"
            else:
                note = " (without Postgres: the container did not start)"
        elif postgres:
            note = " (without Postgres: docker not found; its tests are skipped)"
        if self.which("docker"):
            env["ARGUS_TEST_DOCKER"] = "1"                   # as in ci.yml (OP-014): the Docker tests run, not skip
        try:
            code, out = self.run([self.py, "-m", "pytest", "-o", "addopts=", "-q", "-rfEs", "-p", "no:cacheprovider"], cwd=self.src,
                                 env=env, timeout=3600)
            if code == 0:
                return Result("tests", "pass", _summary(out) + note)
            log = Path(tempfile.gettempdir()) / f"argus-localci-tests-{secrets.token_hex(3)}.log"
            log.write_text(out, encoding="utf-8")
            print(f"  (full pytest output: {log})", flush=True)          # the terminal only, never the PR comment
            failed = re.findall(r"^FAILED (\S+)", out, re.M) + re.findall(r"^ERROR (\S+)", out, re.M)
            if not failed:                                                # a crash, a timeout, a collection error
                return Result("tests", "fail", f"pytest exit {code}: {_summary(out)}" + note)
            code2, out2 = self.run([self.py, "-m", "pytest", "-o", "addopts=", "-q", "--tb=short", "-p", "no:cacheprovider", *failed],
                                   cwd=self.src, env=env, timeout=1800)
            known = [f for f in failed if f.replace("\\", "/") in KNOWN_LOCAL]
            if code2 != 0 and known and len(known) == len(failed):
                return Result("tests", "known-local", f"{_summary(out)}; failing only where known to fail on a laptop: "
                              f"{', '.join(known)}" + note)
            if code2 == 0:
                return Result("tests", "flaky", f"{_summary(out)}; passed alone on a second run: {', '.join(failed)}"
                              + note)
            return Result("tests", "fail", f"{_summary(out)}; failing: {', '.join(failed)}" + note)
        finally:
            if pg:
                self.run(["docker", "stop", pg], timeout=120)

    def _postgres(self) -> tuple[str | None, str | None]:
        name, pw = f"argus-localci-{secrets.token_hex(4)}", secrets.token_hex(16)   # throwaway, never printed
        code, _ = self.run(["docker", "run", "-d", "--rm", "--name", name, "-e", "POSTGRES_USER=argus_owner",
                            "-e", "POSTGRES_DB=argus", "-e", f"POSTGRES_PASSWORD={pw}", "-p", "127.0.0.1::5432",
                            PG_IMAGE], timeout=300)
        if code != 0:
            return None, None
        for _ in range(60):
            if self.run(["docker", "exec", name, "pg_isready", "-U", "argus_owner", "-d", "argus"], timeout=30)[0] == 0:
                break
            time.sleep(1)
        code, out = self.run(["docker", "port", name, "5432/tcp"], timeout=30)
        port = out.strip().splitlines()[0].rsplit(":", 1)[-1] if code == 0 and out.strip() else None
        if not port:
            return name, None
        return name, f"host=127.0.0.1 port={port} dbname=argus user=argus_owner password={pw}"

    def promql(self) -> Result:
        if not self.which("docker"):
            return Result("promql", "skipped", "docker not found (promtool runs in Docker)")
        code, out = self.run(["docker", "run", "--rm", "--mount",
                              f"type=bind,source={self.src / 'tests' / 'promql'},target=/work,readonly",
                              "--entrypoint", "promtool", PROM_IMAGE, "test", "rules", "/work/op005_test.yml"],
                             timeout=600)
        return Result("promql", "pass" if code == 0 else "fail", _tail(out, 1 if code == 0 else 5))

    def frontend(self) -> Result:
        npm = self.which("npm")
        if not npm:
            return Result("frontend", "skipped", "npm not found")
        npx = self.which("npx") or npm
        # CI's job `frontend` (T-0016): lint, unit tests, build, the Playwright browser, the acceptance tests
        steps = [(npm, ["ci"]), (npm, ["run", "lint"]), (npm, ["test"]), (npm, ["run", "build"]),
                 (npx, ["playwright", "install", "chromium"]), (npm, ["run", "e2e"])]
        for tool, args in steps:
            code, out = self.run([tool, *args], cwd=self.src / "frontend", timeout=1200)
            if code != 0:
                return Result("frontend", "fail", f"npm {' '.join(args)}: {_tail(out, 5)}")
        return Result("frontend", "pass", "npm ci, lint, test, build, e2e")

    def verify_main(self) -> Result:
        if not self.which("gh"):
            return Result("main-guard", "skipped", "gh not found")
        return self._brain("main-guard", "verify-main", "--ref", "HEAD")

    def all(self, main: bool = False) -> list[Result]:
        steps = [self.audit, self.lint, self.secrets, self.tests, self.promql, self.frontend]
        out = []
        for step in steps + ([self.verify_main] if main else []):
            r = step()
            print(f"  {r.name:<10} {r.status:<8} {r.detail}", flush=True)
            out.append(r)
        return out


def overall(results: list[Result]) -> str:
    return "FAIL" if any(r.status == "fail" for r in results) else "PASS"


def report(sha: str, results: list[Result], pr: int | None = None, ref: str | None = None) -> str:
    where = f"PR #{pr}" if pr is not None else (ref or "HEAD")
    lines = [f"LOCAL CI {overall(results)} {sha[:12]} ({where}, commit {sha})", "",
             "| step | result | detail |", "|---|---|---|"]
    lines += [f"| {r.name} | {r.status} | {r.detail.replace('|', '/')} |" for r in results]
    skipped = [r.name for r in results if r.status == "skipped"]
    flaky = [r.name for r in results if r.status in ("flaky", "known-local")]
    lines.append("")
    lines.append("Run with `ops/local_ci.py` (the checks of `.github/workflows/ci.yml`)"
                 + (f"; skipped: {', '.join(skipped)}" if skipped else "")
                 + (f"; flaky or known-local: {', '.join(flaky)}" if flaky else "") + ".")
    return "\n".join(lines)


def _git(*args: str, cwd: Path = REPO) -> str:
    code, out = run(["git", *args], cwd=cwd, timeout=300)
    if code != 0:
        sys.exit(f"local_ci: git {' '.join(args)} failed: {_tail(out, 3)}")
    return out.strip()


def _commit(a) -> str:
    """The commit to check: the PR's last push, origin/main, or this checkout's HEAD (its working tree clean)."""
    if a.pr is not None or a.main:
        _git("fetch", "-q", "origin", f"pull/{a.pr}/head" if a.pr is not None else "main")
        return _git("rev-parse", "FETCH_HEAD")
    if _git("status", "--porcelain"):
        sys.exit("local_ci: the working tree is not clean; commit or stash first (the result must match a commit)")
    return _git("rev-parse", "HEAD")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pr", type=int, help="check this pull request's last push")
    ap.add_argument("--main", action="store_true", help="check origin/main and run verify-main (the main-guard job)")
    ap.add_argument("--post", action="store_true", help="post the result as a comment on --pr (gh)")
    a = ap.parse_args(argv)
    if a.post and a.pr is None:
        ap.error("--post needs --pr")
    sha = _commit(a)
    # always a clean temporary worktree of that commit (#111 review): the checks see exactly the commit's files, never
    # this checkout's ignored ones (.venv, node_modules, brain/execution/current/output.bash) that gitleaks would scan
    tmp = Path(tempfile.mkdtemp(prefix="argus-localci-"))
    _git("worktree", "add", "-q", "--detach", str(tmp / "src"), sha)
    src = tmp / "src"
    print(f"local_ci: checking {sha[:12]} in a clean worktree", flush=True)
    try:
        results = LocalCI(src).all(main=a.main)
    finally:
        run(["git", "worktree", "remove", "--force", str(tmp / "src")], cwd=REPO, timeout=300)
        shutil.rmtree(tmp, ignore_errors=True)
    text = report(sha, results, pr=a.pr, ref="origin/main" if a.main else None)
    print("\n" + text)
    if a.post:
        code, out = run(["gh", "pr", "comment", str(a.pr), "--body", text], cwd=REPO, timeout=120)
        print("posted to PR" if code == 0 else f"local_ci: posting failed: {_tail(out, 3)}")
    return 0 if overall(results) == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
