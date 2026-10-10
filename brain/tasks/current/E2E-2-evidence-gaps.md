# E2E-2 — Close the two evidence gaps the runner found (SC-05 disk mount, SC-07 assigned network)

| Field | Value |
|---|---|
| Status | `done` 2026-10-10 — step 1 (code and tests, offline); step 2 (vm-095's agent rebuilt, re-run: SC-07 5/5, SC-05 4/5 with the miss read) |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Found by | [E2E-1 step 3](E2E-1-catalogue-sc04-06.md): SC-05 6/10, SC-07 6/10 over two batches |
| Architecture | no change (no ACR): a capability's default and one inventory field; read-only, no new access |
| Branch | `task/E2E-2-evidence-gaps` (from `main`) |
| Owner | `juanbetancurm` (+ agent), quality lane |
| Needs the VM lease | step 2: **both** (an agent rebuild on vm-095), then vm-166 for the re-run |

## Goal (plain language)

Both misses were the model reasoning correctly on missing evidence. Give it the fact it was missing.

- **SC-05:** the detector fires on the worst *declared* mount (the lab filesystem, 92.6 %), but `host.disk_usage`
  read `/` by default (28 %), so the model saw a contradiction and escalated.
- **SC-07:** the backend's assigned network existed only as a comment, so the model guessed which container was
  misplaced.

## Step 1 (done, offline)

- `host.disk_usage`: `mount` is optional; **without it the capability reads every declared mount** of the host and
  shows each (`vm-166:/ used=28.0%; vm-166:/srv/argus-lab-fill used=92.6% …`). An explicit mount works as before and
  an undeclared one is still refused; a host with no declared mount refuses a read without one. The tool's
  description says so, so the model knows.
- **Declared networks:** the inventory field `networks` (`TargetInfo.networks`); `container.status` adds
  `declared_networks=…` and, when the container is not on one of them, `NOT on its declared network(s): …`. An extra
  network is not flagged. Declared for SC-07's client and backend: `argus-lab-app` (the backend's assigned network;
  the scenario puts it on `argus-lab-iso`).
- Tests: `tests/test_e2e2_evidence_gaps.py` (8; red seen 6/8: no `networks` on `TargetInfo`, the default mount `/`;
  the other two check unchanged behaviour). The SC-05, SC-07, core and evaluation tests pass; the baseline evaluation
  is unchanged (45/47, the two known baseline misses; hard 0 0 0).

## Step 1b (review follow-up, `conantkd`, 2026-10-10; branch `task/E2E-2-disk-partial`)

Found in #70's review: without a mount, one failing mount failed the whole read. The host-probe answers 409 when the
lab filesystem is not mounted (`ops/lab-fill-mount.sh --remove`), so the model would also lose `/`, which the old
default always returned. Now a mount that cannot be read is shown as `vm-166:/srv/argus-lab-fill unavailable (…not
mounted…)` and the others are still read (G-007, RB-005: an unmounted filesystem is an explicit state). The read
fails only when every mount fails; an explicit mount fails as before. `source_time` is the oldest read.
Tests: 4 more in `tests/test_e2e2_evidence_gaps.py` (red seen 2/4: the whole read failed, the first read's time; the
other two pin unchanged behaviour).

## Step 2 (done 2026-10-10, `conantkd`, both leases)

1. vm-095 with **both leases**: backup, `deploy.sh main`, rebuild agent, worker and scheduler, `argus db check`,
   `/healthz`, NO INTERFERENCE. No migration, no change on vm-166.
2. vm-166: `ops/e2e/run.py --runs 5 SC-05 SC-07`. Done when both reach 5/5 (or the misses are read and explained).

**Result** ([evidence](../../execution/history/E2E-2/step-02/evidence.md)): both VMs on `main` `0f076f2`; vm-095's
agent, worker and scheduler rebuilt (backup `argus-20261010T220044Z.dump`, 20/20 db checks, WRITE GATE CLOSED, NO
INTERFERENCE). Batch 22:27-23:30 UTC: **SC-07 5/5** (before 6/10), **SC-05 4/5** (before 6/10), 0 errors, NO
INTERFERENCE after every run. Both gaps are closed: every SC-05 run read the full filesystem (no escalation on a
contradiction), every SC-07 run named the backend. The SC-05 miss (`inc_de65a12688bc`) is another gap: the model did
not read the filler's logs, nothing else links the filler to `/srv/argus-lab-fill`, so it named the host and said the
writer was unproven. Possible general fix, not in this task: `container.status` reports the container's host mounts.
