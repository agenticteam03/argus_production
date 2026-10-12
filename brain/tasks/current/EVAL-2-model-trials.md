# EVAL-2 — The configured model on all 55 evaluation cases, and the fixes it showed (§21.2)

| Field | Value |
|---|---|
| Status | `done` 2026-10-12 — E.1-E.4 on vm-095; the class-registry decision is the team's (below) |
| Phase | 6 / 12 — the §21.2 evaluation ([T-0025](T-0025-evaluation.md) step 3, again) |
| Architecture | [ACR-0008](../../architecture/changes/ACR-0008-stopped-writer-suspect.md) (1.8.7): a stopped writer is a `confirm_then_reason` suspect |
| Branch | `task/EVAL-2-model-trials` (from `main` `48a895b`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | vm-095 only (one-off evaluation containers; the running agent is not rebuilt) |

## Goal (plain language)

The model ran 5 trials on 30 cases on 2026-10-09. Since then 25 cases were added (cpu, nginx, blind spot, dependency,
and 8 disk cases from EVAL-1), so `cpu_saturation`, `nginx_upstream_failure`, `monitoring_blind_spot` and
`disk_pressure` had never been measured against the baseline (§3 "Enablement"). Run all 55 cases, read every miss,
fix what is wrong (the agent, the prompt, the dataset or the harness), and measure again.

## Steps

1. **E.0-E.2 (before), step 01.** State probe; 1 trial (48/55, disk 0.38); 5 trials (0.83, core 0.87; disk 0.45).
   [Evidence](../../execution/history/EVAL-2/step-01/evidence.md).
2. **Fixes (offline, tests red first).**
   - `confirm_then_reason` also reads the logs of an **exited** rw writer of the full filesystem (ACR-0008); the
     baseline keeps running writers only.
   - **System prompt:** a host-level symptom is not a root cause by itself; the host is not named as root cause only
     because no container or process was found; a container's own fault can be the cause of its own failure. Three
     versions were tried with one trial each (step 02's table): the first two over-escalated.
   - **Dataset:** `disk-filler-read-only` (its log claimed the writes on a read-only mount) and `disk-filler-stopped`
     (a "no history" filler logging `done`) contradicted their labels; the logs were fixed, the **labels unchanged**.
     Found after seeing answers, recorded here for that reason.
   - **Harness:** each replay removes its throwaway SQLite store (275 runs filled the container's 64 MiB `/tmp`).
3. **E.3-E.4 (after), step 02.** 1 trial ×3 prompt versions, then 5 trials: **0.93, core 0.95, abstention 0.96**,
   disk 0.97, hard 0 0 0. [Evidence](../../execution/history/EVAL-2/step-02/evidence.md).

## Results (5 trials per case, mean accuracy per class)

| Class | Baseline | Model before (E.2) | Model after (E.4) | §21.2 rule (match or beat the baseline) |
|---|---|---|---|---|
| `cpu_saturation` | 1.00 | 1.00 | **1.00** | matches: keep the model |
| `monitoring_blind_spot` | 1.00 | 1.00 | **1.00** | matches |
| `postgresql_connection_exhaustion` | 1.00 | 1.00 | **1.00** | matches |
| `disk_pressure` | 0.88 | 0.45 | **0.97** | beats (worst trial 0.88) |
| `nginx_upstream_failure` | 1.00 | 0.96 | 0.96 | 1 of 25 escalated |
| `dependency_unavailable` | 1.00 | 0.96 | 0.92 | 2 of 25 escalated |
| `container_restart_loop` | 0.83 | 0.80 | 0.80 | `restart-sigkill-01` escalated 5/5 |
| `health_check_failed` | 1.00 | 0.68 | 0.80 | 4 of 5 misses are wording ("health probe") |
| overall (core) / abstention | 0.95 / 0.89 | 0.83 (0.87) / 0.93 | **0.93 (0.95) / 0.96** | abstention ≥ 0.9: met for the first time |

**Not applied here (team decision, as in T-0025):** switching a class to `baseline` is a registry data change. The
baseline's rules were written with these cases, so the comparison favours it; four classes sit 0.04-0.20 under it,
mostly by an escalation (safe) or a word. Hard counts are 0 in every run.

## Open after EVAL-2

- `restart-sigkill-01`: the model sees exit 137 with OOMKilled=false and escalates instead of naming an outside kill
  (5/5 here, 4/5 on 2026-10-09). A runbook question (RB-008: what exit 137 without OOM means), not a prompt one.
- The word checks ("health check" vs "health probe") still need §21.2's rubric-scored evidence support.
- `eval-run.sh`'s summary was lost twice (an SSH drop, then the crash): run it under `nohup` and keep the full log.
