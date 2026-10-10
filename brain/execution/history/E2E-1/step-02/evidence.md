# E2E-1 step 02 — evidence: the runner's first batch on vm-166 (2026-10-10, juanbetancurm, session cf7b8b638801)

Run from the laptop with `ops/e2e/run.py` (`code.bash` in this folder). Both VMs on `main` `ebbe9c9` (DEPLOY-MAIN-2).
vm-166's lease and marker: `juanbetancurm`; vm-095's lease: `conantkd` (no change to the agent during the batch).
Every run: session marker checked, `nonint-check` before, pre-gate, start, the detector's gate, `POST
/api/v1/investigations` through the runner's tunnel to vm-095, grade, reset (always), `nonint-check` after. Sanitized:
no addresses, no secrets.

## Before

| Check | Result |
|---|---|
| vm-166 state probe | `ref=main`, `commit=ebbe9c9`, `LAB BASELINE OK`, no scenario container left over, the lab filesystem mounted (1 % used), `nonint-check before` saved |
| SC-04 trial (1 run) | **PASS** `inc_52df2de039c8` (331 s): the new catalogue entry works end to end |

## Batch 1: 5 runs each of SC-07, SC-04, SC-06, SC-05 (13:23-16:12 UTC)

| Scenario | Pass | Runs (incident, seconds) |
|---|---|---|
| SC-07 a healthy backend on the wrong network | **4/5** | PASS `inc_a56fda01d2a2` 69, PASS `inc_ac1156f8eb2f` 107, PASS `inc_f32ffe392310` 69, **FAIL** `inc_e7e415955549` 85, PASS `inc_b993d02f0062` 84 |
| SC-04 database sessions leaked | **5/5** | `inc_fde369a74ff4` 326, `inc_0e28b6adc3b4` 362, `inc_8d68f9580c20` 362, `inc_93856b6b0108` 389, `inc_3877669876b2` 393 |
| SC-06 CPU quota | **5/5** | `inc_b2fd1dfcdd8d` 673, `inc_f3179ba82e56` 1259, `inc_115f3c3fcb70` 863, `inc_1d7033847bcf` 893, `inc_338bd0aa7124` 861 |
| SC-05 disk almost full | **3/5** | **FAIL** `inc_3e6af419ab13` 642, PASS `inc_e95c47cbfdc9` 649, **FAIL** `inc_c18ea3c6bcf3` 655, PASS `inc_e2898dc38770` 659, PASS `inc_214ad2aea7f8` 654 |

**17/20 PASS, 0 errors.** Every reset succeeded and every `nonint-check after` was NO INTERFERENCE (the runner stops
the batch otherwise). Detection, class and first runbook were right in all 20 runs: every miss is in the model's
conclusion.

## The three misses

| Run | What the grader saw | Reading |
|---|---|---|
| SC-07 run 4 | diagnosed `dependency_unavailable`, RB-003, root cause **`argus-lab-client`** (expected `argus-lab-backend`) | the misconfiguration is *between* the two (the client's network does not reach the backend's); once in five the model put the fault on the client side. A wrong root cause, stated as a diagnosis |
| SC-05 runs 1 and 3 | `no_action_escalated`, `disk_pressure`, RB-005, **no root cause** (expected `argus-lab-filler`) | the model abstained instead of naming the writer: a safe miss (an escalation, never a wrong claim) |

Not yet read: the evidence of the three incidents on vm-095 (why the writer was not named in SC-05; what the model
read in SC-07 run 4). That reading is the next step, before any change to prompts, rules or labels.

## After

The lab was clean after every run (the runner's reset); vm-166's lease stays `juanbetancurm`'s. Results file kept by
the runner outside the repository (JSON lines, one per run).
