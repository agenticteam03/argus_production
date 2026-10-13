## 2026-10-12 — AFTER-MERGE: both VMs on main d34f0cb (#97–#111)

Type: deployment
Who: conantkd (+ agent; the agent ran the blocks over ssh)
Context: the VMs ran `task/T-0019-batch3b-host-verbs` `9ac49ec` (3a + 3b) while #97–#111 were merged. `juanbetancurm`
asked in #110 not to deploy `main` before #110 (redactor: only declared paths readable) and #109 (`/tcp` 8 s budget).
Both merged; #111 (local CI) adds only `ops/local_ci.py` and docs.
Decision / result: both VMs on `main` `d34f0cb`: target services rebuilt on both; on vm-095 one backup, then agent,
worker and scheduler recreated together on one image. Checks: 20/20 database, 55/55 phase 3, write gate closed,
LAB BASELINE OK and NO INTERFERENCE on both; the 3c routes and the agent's 3c reads answer; the snapshot is in the
catalogue; the redactor keeps the declared nginx path and masks a URL-path secret.
Consequences: the deployment matches `main` again. Next on the VMs: measure EVAL-5 and the snapshot (model calls).
References: [evidence](../../execution/history/AFTER-MERGE-main/step-01/evidence.md), session `4f8a9d4f8dc1`.

### Next step

Measure EVAL-5 and the diagnostic snapshot on vm-095 (needs the lease). Open findings for later tasks: #110 review
(a declared directory matched without a left boundary) and #111 review (`PASS` with every step skipped; gitleaks
scans ignored files without `--pr`).
