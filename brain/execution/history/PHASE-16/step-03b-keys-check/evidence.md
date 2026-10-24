# PHASE-16 step 03b — evidence: how many security keys each enabled operator holds (vm-095, 2026-10-23 UTC, conantkd)

Goal: ACR-0018 D3 asks for two WebAuthn credentials per privileged person. The team reported them registered after the
enrolment tickets ([step 03](../step-03-enrolment/evidence.md)); this reads the database to check. Run by conantkd on
vm-095 with the lease of session `1c60b890bf65` (vm-095 only). Commands: [`code.bash`](code.bash). It prints counts
only: no credential id, key or name of a key. The results below were pasted into the chat, not into `output.bash`.

| Block | Observed | Result |
|---|---|---|
| KY.1 | `{'conantkd': 2, 'juanbetancurm': 1, 'juanes6554': 2}`; `VERDICT: KY.1 STOP: someone has fewer than two keys` | **STOP** (as designed: one operator has one key) |
| KY.3 | `NO INTERFERENCE: non-Argus objects unchanged`; `VERDICT: KY.3 PASS` (KY.1 stopped before its own non-interference check, so it is run apart) | PASS |
| KY.2 | the lease of vm-095 released (`brain.py status`: `released by conantkd`) | done |

## Notes

1. **Two of the three have two keys; `juanbetancurm` has one.** Until the second is registered, `privileged_ready` is
   false for that person (ARCHITECTURE §17.3, D3), so no privileged permission is effective for them. Nothing
   privileged exists yet. A repeat of KY.1 after the second key turns the verdict into PASS.
2. The tickets' own record is [step 03](../step-03-enrolment/evidence.md). The counts here are the database's, not a
   report.
