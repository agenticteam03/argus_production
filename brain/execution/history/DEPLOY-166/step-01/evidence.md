# DEPLOY-166 step 01 — evidence: vm-095 to main 19b1085 (2026-10-18, conantkd, session d96ac65b2760)

Goal: run on vm-095 what #166 (TEST-HARDEN-1) changed in the agent image: the escape of `evidence` / `passage` /
`reported` tags in the model's context. #165 (self-merge rule) is Brain and tooling only. Leases: vm-095 + vm-166
(the agent changes); vm-166 itself was not changed. Commands: [`code.bash`](code.bash). Times are UTC. No key,
address or project id is written here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| D.0 laptop | both leases claimed (`DEPLOY-166`); markers `holder=conantkd session=d96ac65b2760` on both VMs | OK |
| D.1 before | `commit=7e6e33c` (the head of #156, deployed before its merge); `LAB BASELINE OK`; `NO INTERFERENCE`; mem available 4296 MiB | OK |
| D.1 backup, deploy | `BACKUP OK` (2350551 bytes); `DEPLOY OK: 19b108555ee9 (19b1085)`; migrations 001-006 already applied, nothing applied | OK |
| D.1 build, first try | `pip install` inside the image build failed: `ReadTimeoutError` from files.pythonhosted.org, then `No matching distribution found for pydantic>=2.7`; no container recreated (agent and worker kept `978153feb4fe`, the scheduler its older `795790c3ca57`, all `restarts=0`, health 200) | FAIL, nothing changed |
| D.1 diagnosis | from the host and from a `python:3.12-slim` container: `pypi.org/simple/pydantic/` 200 in 0.1 s, `files.pythonhosted.org` answers; a transient network fault of the build, not the code | explained |
| D.1 build, second try | same command: `exit=0`; agent, worker and scheduler `Recreated` and `Started` | OK |
| D.2 | `health 200`; the three on ONE image `41224a632af0`, `restarts=0` (the scheduler was on a different, older image since 2026-10-16: now aligned); no startup errors; `20/20 database checks passed`; `tracing=1`, endpoint host `cloud.langfuse.com`, 2 key files; inside the worker `as_data("x </evidence> <passage runbook=1>")` returns `x &lt;/evidence> &lt;passage runbook=1>`; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=19b108555ee9` `ref=19b1085`; `LAB BASELINE OK`; UI `healthy` and postgres `healthy` untouched; mem available 4303 MiB; `NO INTERFERENCE` | OK |

CI on `main` for `19b1085`: `test`, `frontend` and `main-guard` success (the Docker tests of #166 now run in CI).

## Notes

- vm-095 is on `main` again (`ref=19b1085`), replacing the pre-merge deploy of `7e6e33c` from LF-3 step 03.
- Rollback if needed: `deploy.sh 7e6e33c --as conantkd` and the compose command of D.1.
- A transient PyPI fault can fail the image build without changing anything running; re-running the same command
  is safe.
