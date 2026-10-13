# ACR-0008 — `confirm_then_reason`: a stopped writer of the full filesystem is a suspect too

| Field | Value |
|---|---|
| Status | `accepted` (applied in architecture 1.8.7) |
| Proposed by | `conantkd` (+ agent) · 2026-10-12 |
| Accepted by | `juanbetancurm` · 2026-10-12, by the approval of PR #89 |
| Second approval (safety principle only) | not needed (no safety principle is touched) |
| Architecture version | from `1.8.6` → `1.8.7` |
| Task / PR | EVAL-2 · PR to be opened |

## 1. Detect and explain

The §21.2 evaluation with the configured model, one trial on the 55 cases (EVAL-2 step 01, vm-095, 2026-10-12):
`disk-filler-stopped-with-history` failed. The filler has exited, its logs show it filled `/srv/argus-lab-fill`, and
the data stays, so it is still the cause (EVAL-1's label). The model read the disk usage and the filler's status
(`state=exited`, `host_mounts=/srv/argus-lab-fill(rw)`), did **not** ask for its logs, and named the host. ACR-0007's
confirmation round did not run, because its suspect is a *running* container only.

## 2. Why the current architecture is insufficient

§10.3, the `confirm_then_reason` row (ACR-0007): "a **running** in-scope container with the class's flagged resource
mounted read-write". A container that wrote the data and then exited leaves the filesystem full; it is the case the
round exists for, and the rule excludes it.

## 3. Smallest reasonable change

§10.3, the `confirm_then_reason` row: the suspect is "an in-scope container, **running or exited**, with the class's
flagged resource mounted read-write"; the round reads "the suspect's logs, and its resources **when it is running**"
(an exited container has no live resources to read).

The §21.2 baseline is unchanged: its `disk_pressure` rule still names only a running writer whose log read returned
lines (EVAL-1; `disk-filler-stopped-with-history` stays a declared baseline miss).

**Alternatives considered:**
- A: **a prompt line** ("read the logs of a stopped container that mounts the full filesystem"). Why not: E2E-5
  showed the model skips a confirmation read it is only told about; the strategy makes it certain.
- B: **name a stopped writer in a rule, without the model.** Why not: whether an exited container left the data is
  in its logs (EVAL-1's `disk-filler-stopped`: a stopped container that wrote nothing); the model reads them.

## 4. Consequences

- Code: `disk_suspects(view, include_stopped=True)` and `ConfirmThenReasonStrategy` in `orchestration/strategies.py`.
  No change to the skeleton, domain, policy or capabilities. The read goes through `InvokeCapability`, the budgets and
  the audit like any read.
- Cost: one Level 1 read (`container.logs`) per stopped suspect, only when one exists.
- How to reverse it: drop `include_stopped=True` in the strategy (code), or set `disk_pressure` back to `model_loop`
  (a registry data change, §21.2).
- Does it touch a **safety principle** (read-only, write gate, host isolation, evidence integrity, secrets)? **No.**
  The strategy only returns read decisions (§10.3 contract).

## 5. Decision

Proposed by `conantkd` with the EVAL-2 evidence; decided by a teammate's approval in the pull request.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped, changelog line added (with this ACR's link)
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request
