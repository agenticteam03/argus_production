# T-0023 step 02 — evidence (2026-10-09, juanbetancurm, session e2cf6793f614)

Goal: the first real batch of the scenario runner (`ops/e2e/run.py`) on vm-095 and vm-166: H-1, H-2, SC-09, SC-11
once; SC-03 and SC-01 five times each, every run graded and followed by a NO INTERFERENCE check. `code.bash` here
holds the last block (S.5); S.1-S.4 used the same lease, markers and runner commands with `d00e867`.

Key output lines, SANITIZED (no addresses, no secrets, no personal names). Results file: on the laptop, outside the
repository (`~/argus-e2e/t0023-step2.jsonl`).

| Scenario | Runs | Result | Graded |
|---|---|---|---|
| H-1 | 1 | PASS `inc_4f76301c2d6b` | `no_incident`, no model call, reads on vm-166 |
| H-2 | 1 | PASS `inc_25f6f2501383` | `no_incident`, no model call, reads on vm-095 |
| SC-09 | 1 | PASS `inc_0b3140745274` | `unsupported_escalated`, no class, no model call |
| SC-11 | 1 | PASS `inc_ab6812c8187f` | `refused`, no class, no model call |
| SC-03 | 5 | **5/5 PASS** `inc_58d203a5df80`, `inc_ef107d40b14e`, `inc_1491ffc413e6`, `inc_131a66d9c14a`, `inc_58d7963e34b9` (36-78 s each) | `dependency_unavailable`, root cause `vm-166/container:argus-lab-cache`, RB-003 first, every read on vm-166 |
| SC-01 | 5 graded (+1 error) | **5/5 PASS** `inc_3feb9be9dbb8`, `inc_ab1937914370` (with `d00e867`), `inc_ae32ab235ce8`, `inc_105d53fdc1d1`, `inc_d355721a3e4d` (with `4f8ae43`) | `container_restart_loop`, RB-001 first, every read on vm-166 |

**The error (SC-01, 3rd run with `d00e867`).** The laptop's API tunnel dropped (`ConnectionRefusedError`). The run's
reset and its NO INTERFERENCE check still passed; then ssh to vm-166 timed out in the next run's session check and
the batch stopped before that run started anything. A read-only check (both VMs: marker ours, no `argus-lab-worker`
left, the cache up, NO INTERFERENCE) confirmed the lab clean. Fixed in `4f8ae43` (the runner's own tunnel, retries);
the remaining three SC-01 runs passed with it.

**Durations.** A run of SC-01 after another one waits ~10 min in its pre-gate (the restart signal looks back 10
minutes), as designed: a 5-run SC-01 batch takes ~45 min; SC-03 ~1 min per run.

**Result:** step 2 done. SC-01 and SC-03 have 5 graded runs each on the real VMs, NO INTERFERENCE after every run.
