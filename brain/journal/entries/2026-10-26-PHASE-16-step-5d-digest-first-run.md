## 2026-10-26 - PHASE-16 step 5d: the audit digest's first checked run; the daily job on

Type: implementation (deploy step)
Who: conantkd (+ agent)
Context: ACR-0018 step 5. 5a-5c were merged and deployed (DEPLOY-01db0d7) with the job off and no sink set.
Decision / result:
- The OCI sink set in vm-095's `hosts.env` (a copy kept beside it); the scheduler recreated.
- A first run by hand shipped five signed digests (2026-10-21 to 2026-10-25); the audit chain stayed verified.
- Checked without reading the bucket: each object's stored SHA-256 equals the chain's signed digest rebuilt on vm-095,
  every signature verifies and the series has no gap (5/5). The service credential lists the objects and cannot read
  them, as designed.
- `audit_digest: enabled: true` in `schedules.yaml`; the test that kept the shipped file off now expects the daily run.
Consequences: the daily job ships each closed day from now on. Still open in step 5: an outbound allowlist for the
scheduler (OCI-only egress is not yet enforced) and the team's alert receiver.
References: [evidence](../../execution/history/PHASE-16/step-05d-first-run/evidence.md), ACR-0018 §5, #303, #311, #314.

### Test state

On the VM: `shipped 5 digest(s), 0 conflict(s)`, `VERIFIED 5/5`, `AUDIT CHAIN OK: 311 rows chained`. Locally:
`tests/test_phase16_step5_digest.py` passes with the schedule on.

### Next step

After merge: check out the merge on vm-095 and restart the scheduler (`audit digest: every 86400 s` in its log); then
the egress allowlist follow-up.
