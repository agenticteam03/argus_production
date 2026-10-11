# E2E-5 — Confirm the suspected writer before concluding (the SC-05 confirmation read)

| Field | Value |
|---|---|
| Status | `pending` — proposed 2026-10-11 by `conantkd` as the next step, not started |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Found by | [E2E-3 step 2](E2E-3-container-mounts.md): SC-05 3/5, misses `inc_047b8eece8a3`, `inc_81698a6c8fa9` ([evidence](../../execution/history/E2E-3/step-02/evidence.md)) |
| Architecture | to check in step 1: a rule-planned read round inside the model loop is what `plan_then_reason` already does (§10.3); no new access, read-only. If it needs a new strategy hook, it is an ACR |
| Branch | `task/E2E-5-confirm-writer` (from `main`), not created yet |
| Owner | open (quality lane) |
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

### Step 2 (after the merge)

vm-095: backup, `deploy.sh main`, rebuild agent, worker and scheduler; then `ops/e2e/run.py --runs 5 SC-05` on vm-166
(about 55 minutes). Done when SC-05 is 5/5, or the misses are read and explained.

## Limits

With two writers on one filesystem, both are read, and the model still has to tell them apart from the logs and the
resources. A writer that logs nothing still leaves the decision to the model.
