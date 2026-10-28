# DEMO-X2 step 01 — second deployment window (2026-10-28 UTC)

Operator: conantkd (+ agent over SSH); session `de222ef12a94`; both leases claimed.
Target commit: `9798950bf6b0d7b3c26bd7699b39469d6e7ecdbc` (`main`).
Previous deployed commit on both hosts: `7f137daa836f575c218515c9ec3e8679c0db83c8`.

Observed verdicts (sanitized):
- Before: `LAB BASELINE OK` on both; `NO INTERFERENCE` on both; vm-095 `WRITE GATE CLOSED`.
- Backup: `BACKUP OK`; `VERIFY OK: 31 tables, 34110 rows match`.
- `DEPLOY OK: 9798950bf6b0` on both; clean checkouts at the exact commit.
- vm-095 Compose: tunnel, agent, worker and scheduler built and started. The action network has only
  `argus-v18-tunnel argus-v18-worker`.
- vm-166 Compose: db probe, exporter, host probe, network probe and read gateway built and started.
- The running vm-166 read-gateway image's `/app/service.py` returns Docker's full `Id` as `container_id`
  alongside the 12-character `id` (read-only inspection of the image).
- `94/94 database checks passed` on vm-095.
- `WRITE GATE CLOSED` on vm-095 (`gate_open=0`, `write_capabilities=0`, `action_gateway_resolves=0`
  for all three services); vm-166 `WRITE GATE CLOSED: host-only`.
- `NO INTERFERENCE: non-Argus objects unchanged` on both after deployment.
- Final `deploy.sh status`: `LAB BASELINE OK` on both.

The unqualified write-gate checker on vm-166 first returned `WRITE GATE STOP` because it expects the vm-095
agent, worker and scheduler. Its documented `--host-only` mode passed on vm-166 before and after the deployment.
No action gateway or socket proxy was started and no action credential was created in this window.
