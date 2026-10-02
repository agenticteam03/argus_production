# How to read the output you paste

## pytest

```text
............................ssss                     [100%]
32 passed, 4 skipped in 6.1s
```
- `.` = a passing test, `s` = skipped (e.g. Postgres tests without a database), `F` = failed, `E` = error in setup.
- Look at the **last line**. Anything other than `passed`/`skipped` needs attention; the details are above it,
  starting at `FAILED tests/...::test_name` and the `assert` line marked with `>` and `E`.
- `-rs` shows why tests were skipped.

## docker ps

```text
argus-v18-agent Up 14 hours
argus-v18-postgres Up 14 hours (healthy)
argus-lab-api Up 2 minutes (unhealthy)
argus-lab-worker Restarting (137) 5 seconds ago
```
- `Up` = running; `(healthy)` / `(unhealthy)` = the container's own health check.
- `Restarting (137)` = it keeps crashing; **137** = killed (often out of memory), **1** = the program exited with an error.
- `Exited (0)` = stopped normally.

## docker compose up

- `Container X Started` / `Recreated` = it was (re)started with the new configuration.
- `Container X Running` = nothing changed for that container (it was **not** restarted).
- `CACHED` in the build = that layer was reused; if all layers are cached, the code did not change.

## nonint-check.sh

- `saved /opt/argus-v18/baseline/after.txt (69 lines)` then **`NO INTERFERENCE: non-Argus objects unchanged`** → OK.
- Anything else prints the differing lines: **stop** and analyse them before doing anything else.

## argus diagnose (formatted)

The stages are the real workflow nodes: `DETECT` (class, findings) → `RECALL` (runbooks with ID and version) →
`INVESTIGATE` (the strategy's decision) → `ACT` (each read: host, executor, status, one-line result) → … →
`RECORD` (outcome, root cause, diagnosis, cited evidence). The last lines give the `incident inc_…` id and the
`outcome`. `--raw` prints the same run as JSON lines (run events, model requests/replies redacted, evidence, audit).

## SSH and Git messages

- `Permission denied (publickey)` → wrong key or alias; check `~/.ssh/config`.
- `client_loop: send disconnect` → the connection dropped; reconnect and check whether the last command finished.
- `! [rejected] … (non-fast-forward)` → someone pushed first; for the `session` branch this means the lease is taken.
