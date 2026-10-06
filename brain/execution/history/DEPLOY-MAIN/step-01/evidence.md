# DEPLOY-MAIN step 01 — evidence (2026-10-06, run by conantkd, session 6b413ecc1488)

Both VMs moved to `main` (`09f5ab1`), the agent rebuilt on vm-095, H-1 and SC-03 re-run on the final T-0013 code
(LangGraph runner, review fix "one read per graph step", OP-006). No password in any archived
output.

| Block | Expected | Observed | Result |
|---|---|---|---|
| D.0 lease + markers | lease claimed, same marker on both VMs | `Lease CLAIMED by conantkd`; both VMs `holder=conantkd session=6b413ecc1488` | OK |
| D.1 vm-166 → main | `DEPLOY OK`, no vm-166 rebuild | `DEPLOY OK: 09f5ab10f840 (main) on argus-vm166`; hints: agent + migrations (vm-095 only) | OK |
| D.2 vm-095 → main + agent | migrations already applied, `langgraph`, db 15/15 | `001_init`, `002_checkpoints (already applied)`; image built 26.5 s; `agent runner: langgraph`; `15/15 database checks passed` | OK (after a hang, see below) |
| D.3 H-1 `--check` api | `HEALTHY` | `DIAGNOSED · class dependency_unavailable` (`inc_bee874c1898e`) | unexpected → explained by D.3b |
| D.3b-1 lab state (read-only) | — | `argus-lab-cache Exited (0) 7 hours ago`; `argus-lab-api` unhealthy; Prometheus `argus_container_running{cache}=0`, `argus_container_health_unhealthy{api}=1` | the lab was broken, Argus was right |
| D.4 stop the cache | — | skipped: the cache was already down (SC-03 condition already in place) | SKIPPED |
| D.5 SC-03 diagnose api | `DIAGNOSED`, root cause the cache | `DIAGNOSED · dependency_unavailable`, root cause `vm-166/container:argus-lab-cache`, confidence high, api = victim | **OK — SC-03 verified on LangGraph** |
| D.6 start cache | api healthy, NO INTERFERENCE | api `healthy` after ~20 s; `NO INTERFERENCE` (vm-166); Prometheus `api_unhealthy=0`, 0 firing alerts | OK |
| D.6b H-1 again | `HEALTHY` | `HEALTHY — nothing to do` (`inc_d6ea5d9153a0`) | OK |
| D.7 vm-095 | all argus-* Up, NO INTERFERENCE | all Up, postgres healthy; `NO INTERFERENCE` | OK |

Final state: both VMs `commit=09f5ab10f840…`, `ref=main`; `argus-lab-cache` Up, `argus-lab-api` healthy.

## SC-03 investigation (D.5, trimmed)

```text
step 2 · AI model decides: read → container.status(argus-lab-api), container.status(argus-lab-cache)
  get_container_status  ✓ argus-lab-api: state=running health=unhealthy
  get_container_status  ✓ argus-lab-cache: state=exited
step 3 · AI model decides: read → network.resolve_dns(argus-lab-cache), network.tcp_connect(argus-lab-cache)
  check_dns             ✓ dns argus-lab-cache from vm-166 app network: FAILED
  check_tcp_connection  ✓ tcp argus-lab-cache:6379 from vm-166 app network: FAILED
step 4 · AI model decides: conclude (confidence high, root cause vm-166/container:argus-lab-cache)
outcome: DIAGNOSED · class dependency_unavailable
root cause: vm-166/container:argus-lab-cache · confidence high
"... The API is the victim ... Do not restart or mutate services based solely on this diagnosis."
```

Every read targeted vm-166 only, one read per graph step, and the diagnosis recommends no mutation (read-only phase).

## Problems on the way

1. **`db-migrate.sh | tail -3` hung** (D.2). `ops/db-migrate.sh` runs `docker exec -i … psql`: with `-i`, docker
   reads the terminal (the rest of the pasted block). `pg_stat_activity` showed no session from it, so nothing was
   half-applied. Fix: `sudo bash …/db-migrate.sh < /dev/null`, and no `| tail` (it hid the hang). Every
   `argus diagnose` through `docker exec -i` in `code.bash` now also gets `< /dev/null`. New TROUBLESHOOTING entry.
2. **The lab was not in its baseline state at the start**: `argus-lab-cache` had been stopped for about 7 hours
   (most likely since the SC-03 class demo, whose restart step was not part of the archived output), so the first
   H-1 was, correctly, not healthy. Our tooling had no way to notice it: `nonint-check.sh` only covers non-Argus
   objects and the state probe does not check `argus-lab-*` health.
   Improvement for everyone: end every scenario with its undo plus a health check, and add `argus-lab-*` health
   to the state probe.
3. Operator slips, no effect: a D.2 re-run (same commit, same hang, Ctrl+C), D.5 first pasted on vm-166
   (`No such container: argus-v18-agent`, nothing ran), `brain.py renew` before `start` (refused, no lease).
