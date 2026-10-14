# OP-008 step 03 — evidence: the approved `prune --apply` on vm-095 (2026-10-14, conantkd)

Run by conantkd on vm-095 ([`code.bash`](../../OP-004/step-04/code.bash), shared with OP-004 step 04). Approved by
juanbetancurm in PR #138: one `prune --apply` with `KEEP=7`. Sanitized: no addresses, no secrets.

| Check | Expected | Observed |
|---|---|---|
| Before | `LAB BASELINE OK` | `LAB BASELINE OK` |
| Fresh backup | `BACKUP OK`, `VERIFY OK` | `argus-20261014T162458Z.dump` (2151653 bytes): `VERIFY OK: 13 tables, 29001 rows match`; marker written |
| Dry run (`KEEP=7`) | the list to remove | `newest verified (kept): argus-20261014T162458Z.dump`; `PRUNE DRY RUN: 12 backup sets would be removed` |
| Apply | the same list | `PRUNE OK: 12 backup sets removed` (the same 12 names) |
| Removed | the oldest sets | 2026-10-06T18:50Z, 10-09T13:17Z, 10-09T18:38Z, 10-10T02:33Z, 10-10T12:48Z, 10-10T22:00Z, 10-11T13:18Z, 10-11T23:23Z, 10-12T15:04Z, 10-12T17:52Z, 10-12T19:24Z, 10-12T21:02Z |
| Kept | 7 sets, the newest verified among them | 7 dumps from 2026-10-13T03:46Z to 2026-10-14T16:24Z, each with its `.sha256` and `.fingerprint`; `.verified` markers on 10-13T16:13Z and 10-14T16:24Z |
| After | `NO INTERFERENCE` | `NO INTERFERENCE: non-Argus objects unchanged` |

**Against the approval:** the approved list (2026-10-13) named 9 of 16 sets; by today 3 more had aged out of the 7
newest (10-12T17:52Z, 19:24Z, 21:02Z), so the same `KEEP=7` rule removed 12. The reviewer's after-checks: 7 sets
remain and NO INTERFERENCE, both met; **`sha256sum -c` on the newest verified dump after the prune was not run**
(its restore passed minutes before, in S.1). Run it at the next VM session.

**Deviation:** no Brain lease was claimed for this run (see OP-004 step 04).

Backup and verify scheduling remain a separate team decision.
