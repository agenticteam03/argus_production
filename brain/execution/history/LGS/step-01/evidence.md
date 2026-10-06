# LGS step 01 — evidence (2026-10-06, run by conantkd, session 6b413ecc1488)

Scenarios verified before only on the plain runner, now re-run on the **LangGraph runner** with the final `main`
agent (`09f5ab1`, rebuilt by DEPLOY-MAIN; checkouts on `task/lab-baseline-check`, which changes only
`ops/deploy.sh`). Outcomes were cross-checked in the Postgres `incident` table. No password in any archived output.

| Scenario | Incident | Expected | Observed | Result |
|---|---|---|---|---|
| R1 setup | — | restart loops seen by Prometheus | vm-095 SC-02 `restarts_10m=5`, `oom=false`; vm-166 SC-01 `restarts_10m=3`, `oom=true` (gate on Prometheus, TROUBLESHOOTING #17) | OK |
| **SC-02** (vm-095) | `inc_36771c1cc56a` | DIAGNOSED, non-OOM, missing config, RB-008, vm-095 only | DIAGNOSED `container_restart_loop`; exit 1, `OOMKilled=False`; "the required configuration file `/etc/worker/config.yml` is missing"; RB-008 recalled first; 2 reads, both `docker@vm-095` | **OK** |
| **Identity proof** (SC-01 on vm-166 while SC-02 runs on vm-095, same container name) | `inc_9a4913fd71b6` | DIAGNOSED, OOM, RB-001, vm-166 only | DIAGNOSED; exit 137, `OOMKilled=True`; "killed by an OOM condition associated with its configured 64 MiB container memory limit", host not under pressure; RB-001; 6 reads, all `@vm-166` | **OK** |
| **H-2** (vm-095 api) | `inc_c6cf74c0c7a7` | HEALTHY | `HEALTHY — nothing to do` | **OK** |
| **SC-11** (target not in the inventory) | `inc_03310115718d` | refused, nothing read | `REFUSED`: "vm-166/container:argus-api-1 is not in the inventory; nothing was read" | **OK** |
| **SC-10** (vm-095 exporter stopped) | `inc_3f5a3143ad03` | UNDIAGNOSABLE, RB-014 | `UNDIAGNOSABLE → escalated (metrics missing)`: "exporter scrape is down on vm-095 (monitoring blind spot)", RB-014, evidence pack, no diagnosis claimed | **OK** |
| SC-10, other host | `inc_c6bf99ad8fd0` | vm-166 unaffected | vm-166 api `HEALTHY` | **OK** |
| **SC-12** (vm-166 read gateway stopped, SC-01 running) | `inc_29434f3bdef9` | ESCALATED early, no made-up diagnosis | `docker@vm-166 get_container_status ✗ error`; **escalated at step 2** (plain runner: step 3): "the executor is unreachable. Do not restart blindly; have a human restore read access…" | **OK** |
| R3 restore | — | everything back, NO INTERFERENCE | gateway Up, SC-01 and SC-02 removed, exporter Up; both VMs `LAB BASELINE OK` and **NO INTERFERENCE** | OK |

**Result:** on the LangGraph runner, H-1, H-2, SC-01, SC-02, the identity proof, SC-03, SC-09, SC-10, SC-11 and
SC-12 are now verified (one run each). Every scenario that the plain runner passed also passes on LangGraph.

## Notes

- SC-02's diagnosis text calls the victim "the argus-lab-worker read gateway". That wording is wrong (the worker is
  not a gateway), but the root cause, class, runbook and evidence are right. A wording slip by the model. Watch for
  it in the Phase 12 repeated runs.
- The SC-01 signal reached 3 only after Docker had counted 5 restarts (OP-005, approved 2026-10-06, not yet
  implemented). The Prometheus gate handled it.
- One run per scenario. Quality claims still need ≥ 5 runs (Phase 12).
