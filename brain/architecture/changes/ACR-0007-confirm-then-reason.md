# ACR-0007 — `confirm_then_reason`: a rule-planned confirmation round for `disk_pressure`

| Field | Value |
|---|---|
| Status | `accepted` (applied in architecture 1.8.6) |
| Proposed by | `juanbetancurm` (+ agent) · 2026-10-11 (from `conantkd`'s E2E-5 proposal, option 1) |
| Accepted by | `conantkd` · 2026-10-12, by the approval of PR #86 (#80, which carried this ACR, was merged before any approval; its acceptance passed through the retroactive PRs #82 and #85) |
| Second approval (safety principle only) | not needed (no safety principle is touched) |
| Architecture version | from `1.8.5` → `1.8.6` |
| Task / PR | E2E-5 · PR #80 (proposed and applied) · PR #86 (accepted) |

ACR-0006 is reserved for the OP-003 proposal (`NEXT_STEP.md`), so this record takes the next number.

## 1. Detect and explain

SC-05 (disk almost full on vm-166) through the scenario runner, after E2E-2 and E2E-3: **3/5** (E2E-3 step 2). In both
misses (`inc_047b8eece8a3`, `inc_81698a6c8fa9`, read from the store) the model saw `host_mounts=/srv/argus-lab-fill(rw)`
on the running filler and called it *"the likely writer"*, then named the host because *"the evidence does not prove
its write rate"*. It concluded after two reads without the filler's logs; the passes read them. The fact is in the
evidence; the confirmation read is left to the model, and it skips it two times in five.

## 2. Why the current architecture is insufficient

§10.3 lists three registered strategies; `disk_pressure` uses `model_loop` (§3), where the model decides every read.
`plan_then_reason` plans a *fixed first round*, the same for every incident of the class, so it cannot plan reads that
depend on what the first reads found (which container, if any, writes the full filesystem). No registered strategy
plans a round from the evidence. §10.3 allows new strategies ("registered the same way"), and §21.2 makes the strategy
per class a registry entry; the two tables (§3, §10.3) are the record to change.

## 3. Smallest reasonable change

§10.3, the registered strategies table, add a row:

> | `confirm_then_reason` | `model_loop`, but when the evidence names a **suspect** (a running in-scope container whose
> `container.status` shows the class's flagged resource mounted read-write: for `disk_pressure`, a declared filesystem at or
> above the detector's threshold in `host.disk_usage`), the next round is planned by rule: the suspect's
> `container.logs` and `container.resources`, once per suspect; then the model decides | `disk_pressure` |

§3, the `disk_pressure` row: strategy `model_loop` → `confirm_then_reason`.

**Alternatives considered:**
- A: **an attribution rule in RB-005** ("a single running container writing the full filesystem read-write is the
  root cause; confirm it with its logs"). Why not: it only nudges the model; it does not guarantee the read, for the same
  reason E2E-3 did not choose a prompt line.
- B: **`plan_then_reason` with logs in the fixed first round.** Why not: the first round cannot know which container
  to read; reading every in-scope container's logs on every disk incident costs reads and context for nothing.
- C: **keep `model_loop` and accept 3/5.** Why not: the evidence for the right answer is one deterministic read away.

## 4. Consequences

- Code: `orchestration/strategies.py` (`ConfirmThenReasonStrategy`, `disk_suspects`), its registration in
  `infrastructure/wiring.py`, `disk_pressure` in `detectors/classes.py`. No change to the skeleton, domain, policy or
  capabilities (§22 item 12). The round goes through `InvokeCapability`, the budgets and the audit like any read.
- Cost: at most two Level 1 reads per suspect, only when a suspect exists (none for a host with no writer found).
- Risk: with two writers both are read and the model still has to tell them apart; a writer that logs nothing leaves
  the decision to the model, as today.
- How to reverse it: set `disk_pressure` back to `model_loop` in the class registry (a data change, §21.2).
- Does it touch a **safety principle** (read-only, write gate, host isolation, evidence integrity, secrets)? **No.**
  The strategy only returns read decisions (§10.3 contract); policy, budgets and audit are the skeleton's.

## 5. Decision

Proposed by `juanbetancurm` on `conantkd`'s E2E-5 option 1. **Accepted** by `conantkd` on 2026-10-12 with the
approval of PR #86, whose review covered `bfe93c0` (this ACR, PR #80).

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped, changelog line added (with this ACR's link)
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request
