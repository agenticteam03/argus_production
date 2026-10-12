# E2E-5 — Confirm the suspected writer before concluding (the SC-05 confirmation read)

| Field | Value |
|---|---|
| Status | `done` — proposed 2026-10-11 by `conantkd`; step 1 (offline) done 2026-10-11 and step 2 (SC-05 × 5) 5/5 PASS 2026-10-12, by `juanbetancurm` |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Found by | [E2E-3 step 2](E2E-3-container-mounts.md): SC-05 3/5, misses `inc_047b8eece8a3`, `inc_81698a6c8fa9` ([evidence](../../execution/history/E2E-3/step-02/evidence.md)) |
| Architecture | [ACR-0007](../../architecture/changes/ACR-0007-confirm-then-reason.md) (1.8.6): a new registered strategy, no new hook, no skeleton change; read-only, no new access |
| Branch | `task/E2E-5-confirm-writer` (from `main`) |
| Owner | `juanbetancurm` (+ agent), quality lane |
| Needs the VM lease | step 2: vm-095 (agent rebuild), then vm-166 for the re-run |

## Goal (plain language)

Since E2E-3 the model knows which container has the full filesystem mounted read-write. In two of five SC-05 runs it
called that container *the likely writer* and still named the host, because nothing proved the writing. Proof is one
read away (the container's logs or resources), but `disk_pressure` runs `model_loop`, so the model decides whether to
take that read, and in the misses it concluded after two reads. Make the confirmation read happen every time, and let
the model decide with the proof in front of it.

## Proposal

### Option 1 (recommended): a rule-planned confirmation round

When the evidence shows a **suspect** (a running in-scope container whose `container.status` has `host_mounts` in rw
on the filesystem the detector flagged), the next read round is planned by rule, not by the model:
`container.logs` and `container.resources` of each suspect, once. After that, the model loop continues as before.

- Deterministic and general: it works for any class with a "suspected source" in the evidence, not only SC-05.
- It uses the same mechanism `plan_then_reason` already has (a fixed round, then the model), so it may need no ACR.
  Step 1 checks this against §10.3.
- Costs: at most two reads per suspect, and only when a suspect exists.

### Option 2 (cheaper): an attribution rule in RB-005

*"A single running container that writes the full filesystem read-write is the root cause; the host is the victim.
Confirm it with its logs before concluding."* This needs a runbook `version` and `last_reviewed` bump. It only nudges
the model: it does not guarantee the read (the same reason E2E-3 did not choose a prompt line).

## Plan (option 1)

### Step 1 (offline, test first)

- The suspect rule, from the evidence already collected (the detector's mount and the `host_mounts` of
  `container.status`): no suspect → no extra round; a ro mount or a stopped container → not a suspect; the round is
  planned once.
- The `disk_pressure` strategy uses it. The baseline evaluation (+ a case: the suspect's logs are read before the
  conclusion) stays hard 0 0 0.

**As built (2026-10-11):** the §10.3 check found no new hook is needed (a strategy only returns decisions; new ones
are "registered the same way"), but `plan_then_reason` plans a *fixed* first round and cannot depend on what was found,
so it is a new registered strategy, `confirm_then_reason`, and the §3/§10.3 tables change: ACR-0007. A suspect is a
running container whose `container.status` shows `host_mounts` rw on a declared filesystem that `host.disk_usage`
reports at or above the detector's 90 %. The round (its `container.logs` and `container.resources`) is planned once
per suspect, then the model loop decides. Tests: `tests/test_e2e5_confirm_writer.py` (7; red seen: no strategy). The
end-to-end test runs a scripted investigation through the real skeleton: with `confirm_then_reason` the filler's logs
are read after its status and before the conclusion; with `model_loop` they are never read. The `disk_pressure`
evaluation cases (still `AWAITING_CASES`) follow in their own PR.

### Step 2 (done, both leases, session dbc9d75324dd)

vm-095 from `e3286df` to `main` `2a5f06b` on 2026-10-11 (backup OK; agent, worker and scheduler rebuilt, restarts 0;
20/20 database checks; `disk_pressure strategy: confirm_then_reason`; WRITE GATE CLOSED; LAB BASELINE OK; NO
INTERFERENCE). Then `ops/e2e/run.py --runs 5 SC-05`, 2026-10-11 23:25 to 2026-10-12 00:21 UTC: **5/5 PASS** (was 3/5),
0 fail, 0 error. Every run: `diagnosed`, `disk_pressure`, root cause `vm-166/container:argus-lab-filler`, first runbook
RB-005; 610–710 s per run. Incidents `inc_f516947934ac`, `inc_a6b14dc6994d`, `inc_43c6f451068a`, `inc_34a0e7bcbb12`,
`inc_3dc347d2cdc8`. Whether the rule-planned round fired in each run was not read per run; the strategy was live.

Process note: the deploy ran while `main-guard` was red (#84 and #85 merged with no GitHub approval) and before
ACR-0007's acceptance was on record, by `juanbetancurm`'s decision. Both were closed afterwards: #86 (approved by
`conantkd`) and #88 (ACR-0007 accepted).

## Limits

With two writers on one filesystem, both are read, and the model still has to tell them apart from the logs and the
resources. A writer that logs nothing still leaves the decision to the model.
