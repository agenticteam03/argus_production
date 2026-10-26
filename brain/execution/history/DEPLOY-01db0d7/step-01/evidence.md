# DEPLOY-01db0d7 step 01 — evidence: vm-095 to main 01db0d7 (2026-10-26 UTC, conantkd)

Goal: run on vm-095 phase 17's action cards and read-only next-action suggestions (#316) with the vm-095 denial (#318),
phase 16 step 5's audit digest code (#303, #311) and step 5c's wiring (#314: the scheduler mounts the digest key and the
OCI credential, its memory 256m), and evaluation-only code (#300, #319, #329-#333). `audit_digest` stays off. No
migration (#322's 014 is not merged), no UI change; vm-166 does not change. Run by conantkd's agent over ssh at
conantkd's request ("tienes los permisos corre los bloques"), both leases (session `15ed09dd`). Commands:
[`code.bash`](code.bash). Sanitized: no name, address, key or credential content.

| Block | Observed | Result |
|---|---|---|
| D.1 vm-166 | marker; `before` saved (63 lines) | OK |
| D.2 vm-095, first run | `ref=c8d8594`, `LAB BASELINE OK`; `before` saved (54 lines); the key a file; **`oci_digest: MISSING or not a file`**; `STOP`, nothing changed (see note 1) | STOP |
| D.2 vm-095, corrected | the key, `oci_digest/config` and `oci_digest/key.pem` files; sink line in `hosts.env`: 0; evaluations running: 0; `BACKUP OK` (2479595 bytes, 03:45Z); **`VERIFY OK: 22 tables, 33493 rows match`**; `DEPLOY OK: 01db0d75167b (01db0d7)` | OK |
| D.3 vm-095 | agent, worker, scheduler `Recreated`, `Started`; `health 200`; `deploy recorded: 01db0d7 (main) on vm-095 by conantkd` | OK |
| D.4 vm-095 | four `running restarts=0` (the UI untouched); error lines 0, 0, 0; scheduler memory limit 256 MB; **scheduler digest mounts as files: 3**; worker sees no digest file; **`56/56 database checks passed`**; `AUDIT CHAIN OK: 265 rows chained`; **`phase 17 live; denied hosts: ['vm-095']`**; `audit_digest: enabled: false`; `/me` 401; `ref=01db0d7`, `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.5 vm-166 | `NO INTERFERENCE` | OK |
| D.6 laptop | `Lease released on vm-095 and vm-166.` | OK |

## Notes

1. **The prepared D.2 checked `secrets/digest/oci_digest` as a file;** it is a folder (`config` and `key.pem`, as
   `wiring.py` and `policies/SECURITY.md` say). The block stopped before any change, as designed. A read-only check
   found the folder with both files non-empty; D.2 and D.4 were corrected to check the three files and D.2 re-run.
2. **`ARGUS_AUDIT_DIGEST_SINK` is not set in `hosts.env`:** the scheduler has no sink, and the job is off. Turning it
   on is step 5's next action (a first checked run, then `enabled: true`).
3. **Lease:** the vm-095 lease of `juanbetancurm` (T-0047-H4W2) had expired at 00:59Z; conantkd took it over at 01:00Z
   for DEPLOY-7f8c14b, which never ran (the leases expired at 02:17Z). This deploy claimed both leases afresh.
4. **Rollback:** `deploy.sh c8d8594 --as conantkd` and the compose command of D.3.
