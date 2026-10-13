# E2E-4 — SC-08 in the scenario runner's catalogue

| Field | Value |
|---|---|
| Status | `done` — step 1 (the catalogue entry, offline) 2026-10-11 (#77); step 2 (SC-08 × 5 on vm-166) 5/5 2026-10-11, run in E2E-3 step 2 (#78) |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Architecture | no change (no ACR) |
| Branch | `task/E2E-4-catalogue-sc08` (from `main`) |
| Owner | `juanbetancurm` (+ agent), quality lane |
| Needs the VM lease | step 2 only (vm-166) |

## Goal (plain language)

SC-08 (nginx in front of a slow upstream, T-0029) was proven once by hand on vm-166 but was the one planned scenario
missing from `ops/e2e/scenarios.yaml`, so the runner could not repeat it. Same approach as
[E2E-1](E2E-1-catalogue-sc04-06.md).

## Step 1 (done, offline)

- **start:** T-0029's command (`--profile sc08 up -d argus-lab-slow argus-lab-nginx`);
- **gate:** the detector's signal and threshold, `http_gateway_error_ratio_5m` ≥ 0.5 for `argus-lab-nginx`;
- **pre-gate:** no probe samples of nginx in the last 5 minutes (the exporter probes it only while it runs), so run N
  never sees run N-1's 504s;
- **expected:** diagnosed, `nginx_upstream_failure`, root cause `argus-lab-slow`, first runbook RB-015, reads on vm-166;
- **reset:** `docker rm -f argus-lab-nginx argus-lab-slow` only. T-0029's proof used `compose --profile sc08 down`;
  the catalogue never uses `compose down` (it acts on the whole lab project), so the reset removes just the two
  containers the scenario started.

Tests: `tests/test_e2e_runner.py` (red seen: SC-08 missing; 37 pass), including the check that the gate holds the
detector's signal exactly as the agent fills it. `run.py --dry-run SC-08` prints the steps and executes nothing.

## Step 2 (vm-166's lease)

`ops/e2e/run.py --runs 5 SC-08`, alone or with SC-05 after E2E-3's rebuild. Record the result here.
