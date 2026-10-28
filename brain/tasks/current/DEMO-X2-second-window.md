# DEMO-X2 — second deployment window for the demo foundation

| Field | Value |
|---|---|
| Status | `in review` — deployed on 2026-10-28, records await PR review; [evidence](../../execution/history/DEMO-X2/step-01/evidence.md) |
| Owner | conantkd (+ agent) |
| Target | both VMs, exact `main` commit `9798950bf6b0d7b3c26bd7699b39469d6e7ecdbc` |
| Lease | both claimed for the deploy and released after verification and record |

## Goal

Deploy the already merged X-3/X-4 foundation before the first action release: vm-095's internal tunnel and worker
path, and vm-166's target service with a full `container_id` read. Keep the write gate closed.

## Result

The two VM checkouts and relevant services reached the target commit. A vm-095 backup was verified before the
change. Both lab baselines, database checks, write-gate checks and noninterference checks passed. The action gateway
and socket proxy remain unstarted; X-5 handles their token, active configuration and first released pair.

## Evidence and next step

[Step 01 evidence](../../execution/history/DEMO-X2/step-01/evidence.md) records the observed verdicts and the
corrected vm-166 host-only gate check. After this record merges, X-5 may proceed when its CI and required reviews
are satisfied.
