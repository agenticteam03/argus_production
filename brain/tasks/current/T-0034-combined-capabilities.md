# T-0034 — Combined capabilities (§12.7): several reads in one result, every sub-read through InvokeCapability

| Field | Value |
|---|---|
| Status | `in review` — done offline 2026-10-12 (tests); on the VMs with the next AFTER-MERGE |
| Phase | 4 — tools and guarded execution ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change (no ACR): implements §12.7 as written |
| Branch | `task/T-0034-combined-capabilities` (from `main`) |
| Owner | `conantkd` (+ agent); decided 2026-10-12 |
| Needs the VM lease | no (in the worker; verified on vm-095 after the merge) |

## Goal (plain language)

ARCHITECTURE §12.7 describes combined capabilities (`analysis.*`): several observations gathered into one result, run
in the worker, "every sub-call individually validated, budgeted, policy-checked, audited and stored", never reaching
an executor directly, with a `max_subcalls`. The mechanism did not exist; T-0019 batch 3c (option A2) chose not to
build it for one network verb. This task builds it, with its first use.

## Design

- `CapabilitySpec.max_subcalls` (> 0 = combined). `InvokeCapability` runs a combined capability itself, after the
  usual validation, policy and budget for the call, and gives its `impl` a `_SubInvoker` (only `read(name, target,
  arguments)`) instead of an executor client.
- Each sub-read goes back through `InvokeCapability` with the caller `capability:<name>`: validation, policy (scope,
  level, safety class, inspection), `max_per_incident` (the incident's counters are shared), audit, evidence.
- Refused (and audited, rule in brackets): a sub-read past `max_subcalls` (`max_subcalls`); a combined capability
  called from another one (`nested_combined`). A target outside the incident's scope is refused by the policy as usual.
- The combined result is stored as evidence too; its values list the sub-reads' `evidence_id`s (`subcalls`). Both
  runners keep `refs_of(obs, ref)` — the sub-reads first, then the combined record — so the model can cite the
  sub-reads and the LangGraph runner's counters (OP-012) count them.
- **First use: `analysis.diagnostic_snapshot`** (`capture_diagnostic_snapshot`, Level 3, SAFE, in the worker,
  `max_subcalls` 6): a container's status, resources and last 30 log lines, and its host's memory and CPU. Policy
  `max_per_incident: 1`. **Offered to no class yet** (tag `snapshot`): it changes how the model investigates, so it is
  offered after an evaluation batch measures it.

## Tests

`tests/test_combined_capabilities.py`, 8 tests (red seen: no `max_subcalls`, no snapshot, no `refs_of`): every sub-read
goes through `InvokeCapability` and is referenced; `max_subcalls`, nested and out-of-scope refusals are audited; the
budget is shared; the impl gets no executor; the runners keep the sub-reads as citable evidence.

## Next

Offer `capture_diagnostic_snapshot` to a class after an evaluation batch on vm-095 compares it; further combined
capabilities (`analysis.timeline`, `analysis.trace_request_path`) on the same mechanism.
