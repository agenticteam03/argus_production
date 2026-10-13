## 2026-10-12 — LOCAL-CI: every mode checks a clean worktree of the commit (review of #111)

Type: fix
Who: conantkd (+ agent)
Context: the #111 review. Without `--pr` / `--main`, `ops/local_ci.py` ran the checks in the developer's own checkout,
so gitleaks (`--no-git`, a directory scan) also read the checkout's ignored files (`.venv`, `node_modules`,
`brain/execution/current/output.bash`): false positives, and files that are never committed were scanned. The other
note of that review ("PASS when every step is skipped") was overstated: `audit`, `lint` and `tests` never skip (they
need only Python); only `secrets`, `promql` and `frontend` can, and the protocol leaves those to the reviewer. Not
changed.
Decision / result: every mode checks a temporary `git worktree` of the commit (HEAD needs a clean working tree, as
before; the PR's last push or `origin/main` as before), removed at the end.
Consequences: the HEAD mode now sees exactly the commit's files, as CI does; it installs the frontend's packages in
the worktree (`npm ci` did that already).
References: `ops/local_ci.py` (`_commit`, `main`), `tests/test_local_ci.py`.

### Test state

`tests/test_local_ci.py`: 1 test added (red seen: the HEAD mode checked this checkout).

### Next step

Open the PR when a reviewer is available.
