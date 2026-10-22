# DEPLOY-afb72e8 step 01 — evidence: vm-095 to main afb72e8, the EdDSA key mounted (2026-10-22 UTC, conantkd)

Goal: run on vm-095 phase 16 step 2 (EdDSA access tokens with a new Ed25519 key), `db prune-sessions` (#240), T-0047
H4/H5 (H5 offered to no class) and the UI with Vite 8 and the contrast fix (#242, #257). No migration; vm-166 does not
change. Run by conantkd. Commands: [`code.bash`](code.bash). Sanitized: no key, address or token is written here.
Between afb72e8 and the main of the day (096bf90) only `argus/evaluation/replay.py` (the offline replay) and tests
changed, so the prepared commit was deployed as it was.

| Block | Observed | Result |
|---|---|---|
| D.1 vm-166 | `nonint-check before` saved (63 lines) | OK |
| D.2 vm-095 | `SESSION OK`; `ref=6c83da3`, `LAB BASELINE OK`; `before` saved (54 lines); `BACKUP OK` (2433710 bytes, 12:56Z); `DEPLOY OK: afb72e8d0d0d (afb72e8)`, the rebuild hint for agent, worker and scheduler; the key file created with the same owner and mode as `jwt_signing_key` (400 both); `ED25519 Public-Key` | OK |
| D.3 vm-095 | agent, worker, scheduler `Recreated`, `Started`; `health 200`; `deploy recorded: afb72e8 (main) on vm-095 by conantkd` | OK |
| D.4 vm-095 | UI `Recreated`, `Started`; `running health=healthy restarts=0`; ports 80 and 443 only; insights in the bundle 1; the solid button colour in the bundle 1 | OK |
| D.5 vm-095 | three containers `running restarts=0`; error lines: agent 0, worker 0, scheduler 8 (all its `INFO` queries of the `argus_probe_error` metric, not errors: checked by listing them); `mount is a file`; **`EdDSA on`**; **`H5 read registered`**; `/me` without a token 401; `38/38 database checks passed`; `AUDIT CHAIN OK: 124 rows chained, 3893 written before the chain`; the first `prune-sessions` dry run: `sessions=0 revoked=0`; `ref=afb72e8`, `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.6 browser | logged in again (a new EdDSA token); the buttons blue (the shade change, #3b82f6 to #2563eb, is subtle by design) | OK |
| D.7 vm-166 | `NO INTERFERENCE: non-Argus objects unchanged` | OK |

## Notes

- **The scheduler check counts metric names:** `grep -ciE "traceback|error"` matches the scheduler's `argus_probe_error`
  queries (4 per minute). The next deploy's code.bash should exclude them (`grep -v argus_probe_error`) so the count
  means errors only.
- **Every open session had to log in again** once the key was mounted: an HS256 token is refused.
- **Rollback:** `deploy.sh 6c83da3 --as conantkd` and the compose commands of D.3 and D.4 (the key file may stay).
