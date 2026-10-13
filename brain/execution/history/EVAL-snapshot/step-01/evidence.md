# EVAL-snapshot — `capture_diagnostic_snapshot` offered to `health_check_failed`, measured (2026-10-13 UTC)

Run by conantkd's agent over ssh; both leases, session 4f8a9d4f8dc1.

Goal: T-0034 left the snapshot offered to no class "until an evaluation batch measures it". This batch offers it to
`health_check_failed` (the lowest class of the `main` baseline, 0.88) and compares with that baseline.

How: branch `task/EVAL-snapshot` `306a437` (one change: the tag `snapshot` in `health_check_failed`'s tool tags).
On vm-095 an image `argus-v18-agent:snapshot` was built from it in `/tmp` (the checkout and the services untouched:
`checkout local modifications: 0`), then `ARGUS_EVAL_IMAGE=argus-v18-agent:snapshot eval-run.sh --trials 5`: the 55
cases, 5 trials, replayed from fixtures (only the model's API called). Log `EVAL-snapshot.log`, results
`eval-20261013-051706.jsonl`; baseline `eval-20261013-042857.jsonl` (EVAL-main, PR #118: `brain/execution/history/EVAL-main/step-01/evidence.md`).
A first launch failed before running anything (`sudo -E` dropped the deploy key's variable: no image, no run).

| `health_check_failed` (25 runs each) | `main` (no snapshot) | snapshot offered |
|---|---|---|
| accuracy | **0.88** (22 / 25) | **0.72** (18 / 25), worst trial 0.40 |
| runs that used the snapshot | — | 19 / 25 |
| reads per run (sub-reads counted) | 4.60 | 7.80 |
| model calls per run | 3.56 | 3.12 |
| p50 | 10203 ms | 11320 ms |

Overall: 265 → 259 / 275 (0.96 → 0.94), abstention 0.98 both, recall@3 1.00, **hard 0 0 0** both. The other classes
were not offered the snapshot; their differences (dependency 0.92 → 0.88: `dep-backend-stopped` ×2,
`dep-backend-wrong-network` ×1) are run-to-run noise of 5 trials.

The health misses with the snapshot: `health-api-vm095-01` t3, `health-api-vm095-02` t2, t4 (and t5 `diagnosed`),
`health-api-vm166-01` t2, t4, `health-db-vm166-01` t2 — all but one `no_action_escalated`: with the broad snapshot in
hand the model escalated where, with the class's targeted reads, it named the failing check.

**Decision:** the snapshot is **not** offered to `health_check_failed` (the offer is reverted on this branch: the code
is `main`'s). It stays in the catalogue, offered to no class. A broad first look costs the model the focus a
targeted read gives it in this class; another class (or a different composition of the snapshot) would need its own
batch. Left on vm-095: the image `argus-v18-agent:snapshot` (not used by any service).
