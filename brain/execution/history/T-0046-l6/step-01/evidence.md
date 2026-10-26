# T-0046 L6 step 01 — pre-deployment VM state probe (2026-10-25 UTC, conantkd)

Goal: establish the live state and non-interference baseline on both VMs before deploying T-0046. PR #322 was still
open and unmerged, so this step performed only the required state probe; it did not deploy a commit or change services.
The probe commands are archived in [`code.bash`](code.bash).

| VM | Observed | Result |
|---|---|---|
| vm-095 | Session marker accepted; deployed commit `c8d859465f8d5272885b4d0cecaf4d60df14155e`, ref `c8d8594`; agent, worker and scheduler running; `LAB BASELINE OK`; before/after snapshots each 54 lines; `NO INTERFERENCE: non-Argus objects unchanged` | `T0046.1 PASS (3 of 3)` |
| vm-166 | Session marker accepted; deployed commit `bdcd0485e5b4485d2a2ee8f06fcceeb62efe803f`, ref `bdcd048`; lab DB, cache and API running; `LAB BASELINE OK`; before/after snapshots each 63 lines; `NO INTERFERENCE: non-Argus objects unchanged` | `T0046.2 PASS (3 of 3)` |

No migration or application deploy was run. Deployment of migration 014 and the T-0046 agent remains gated on PR #322
being merged. Both leases are released at the end of this step.
