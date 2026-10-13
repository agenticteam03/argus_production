# E2E-9 — SC-12 accepts a diagnosis made without the stopped read gateway

| Field | Value |
|---|---|
| Status | `in review` — code and tests done 2026-10-13 (`task/E2E-9-sc12-host-probe`) |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Architecture | no change (no ACR): the runner's grading and one catalogue entry |
| Branch | `task/E2E-9-sc12-host-probe` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | no (offline); SC-12's next runs use it as usual |

## Goal (plain language)

E2E-8 step 2: SC-12 run 1 (`inc_abe543607681`) was graded FAIL for `diagnosed`. With vm-166's read gateway stopped,
the model read the **host probe** (`host.kernel_oom_records`: six memcg OOM kills of the worker) and named the right
root cause. SC-12's "never `diagnosed`" predates the host probe (T-0019 batch 2); what it must hold is "no diagnosis
without evidence". Option (a), agreed with `conantkd`.

## What changes

- `ops/e2e/run.py`: an expectation may carry `if_diagnosed: {root_cause, executor_down}` (exactly those two keys,
  checked when the catalogue loads). A `diagnosed` result then passes only with that root cause, **no successful read
  through `executor_down`** (else the scenario did not cut it and the run proves nothing) and **at least one
  successful read through another executor**. Other outcomes are graded as before.
- `ops/e2e/scenarios.yaml` SC-12: outcome `no_action_escalated`, `undiagnosable` or `diagnosed`, with
  `if_diagnosed: {root_cause: vm-166/container:argus-lab-worker, executor_down: docker_read}`.

## Tests

`tests/test_e2e9_sc12_host_probe.py`, 11 (red seen: SC-12 without `diagnosed`, no `if_diagnosed`): run 1's reads pass;
an escalation passes; a successful `docker_read` fails; no successful read fails; a wrong root cause fails; the key's
shape; the catalogue entry. `tests/test_e2e8_catalogue.py`: SC-12's assertion follows the new rule.
