# PHASE-16 step 03 (enrolment) — evidence: the first-credential tickets on vm-095 (2026-10-23 UTC, conantkd)

Goal: ACR-0018 decision D4. A password alone never binds a key, so each person's first WebAuthn credential needs a
one-time code issued by another administrator on vm-095 (`argus webauthn allow-enrol`). Run by conantkd on vm-095 with
the lease of session `a8a664a7e486` (vm-095 only; vm-166 not involved). Commands: [`code.bash`](code.bash). Sanitized:
no code, key, address or output with a one-time secret (TK.2's second command printed the codes; its output was not
pasted and did not pass through the agent).

| Block | Observed | Result |
|---|---|---|
| TK.1 | `SESSION OK`; `commit=77c45243…`, `ref=77c4524`, `LAB BASELINE OK`; `health HTTP 200`; `nonint-check before` saved (54 lines) | PASS |
| TK.2 | the principals listed (`conantkd`, `conantkd-viewer`, `juanbetancurm`, `juanes6554`, `olav`); two tickets issued, for `juanbetancurm` and `juanes6554` (single use, 24 h) | done; codes not recorded |
| TK.3 | `ENROL TICKETS AUDITED: 2`; `NO INTERFERENCE: non-Argus objects unchanged` | PASS |
| TK.4 | `Lease released on vm-095.` | PASS (2 of 2) |

## Notes

1. **The first run of TK.1 stopped** with `put the real session id in the first line`: the block compared the SESSION
   file against the same text the person had just replaced, so it always stopped. Fixed in the block (it now looks for
   `session=REPLACE`, which a real id never contains) and the same for the `OTHER` name. The file archived here is the
   fixed version.
2. **The keys, as the database shows them** ([step 03b](../step-03b-keys-check/evidence.md)): `conantkd` 2,
   `juanes6554` 2, `juanbetancurm` 1. Before that check, the team had reported all registered; the counts replace the
   report.
3. The UI's name, the relying party and the tickets' codes appear nowhere in this record.
