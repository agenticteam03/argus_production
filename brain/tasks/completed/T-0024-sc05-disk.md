# T-0024 — SC-05: host disk almost full (`disk_pressure`, RB-005)

| Field | Value |
|---|---|
| Status | `done` 2026-10-09 (steps 1-4: SC-05 DIAGNOSED on vm-166 from the pulled alert); PR #47 merged |
| Phase | 11 — synthetic incidents ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) §7: SC-05); uses phase 7's node-exporter (T-0022) |
| Architecture | no change (no ACR): §3 class table (`disk_pressure` · RB-005 · branch RB-019 · `model_loop`), §4.1 signal templates with a mount parameter, node-exporter (§3.5) |
| Branch | `task/T-0024-sc05-disk`, on top of `task/OP-010-reserved-slot` (vm-166 runs it; T-0022's node-exporter is needed) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | the lab mount, the deploy and the scenario run on vm-166; the diagnosis on vm-095 waits for T-0022 step 5 |

## Goal (plain language)

A workload on vm-166 fills a small lab filesystem until it is almost full. Argus must **detect** it from
node-exporter's metrics, open a `disk_pressure` incident on the host `vm-166/host:vm-166`, read the disk usage,
estimate how fast it fills, and name the filling workload as the cause, without proposing to delete data.

## Decisions (2026-10-08, `conantkd` + agent)

- **A dedicated lab filesystem**, never the root disk: a 256 MiB ext4 file loop-mounted at `/srv/argus-lab-fill`
  (the place the plan reserves, N2; the inventory already declares the mount). The image file lives under
  `/opt/argus-v18/lab/`. Created by `ops/lab-fill-mount.sh` (idempotent, `--remove` undoes it); not in `fstab`:
  after a reboot the mount is absent and every reader reports it as unknown, never as healthy.
- **Signals per declared mount (general):** the templates take `$mounts`, the host target's inventory mounts, so a
  host with a data disk is covered without a new signal. Mount paths are validated in the inventory (no regex
  characters).
- **`rslave` on the host views** (node-exporter `/host`, host-probe `/rootfs`): a mount created after the container
  started is then seen; without it the container would read the root disk under the mount's name, silently. The
  host-probe also refuses a declared mount that is not mounted (unknown, not the root disk's numbers).
- **The filler refuses a filesystem larger than 512 MiB**, so a missing mount can never fill the root disk.
- **The filler `depends_on` the host** in the inventory (it writes to the host's filesystem): the incident scope is
  the target plus its direct dependencies and dependents (ARCHITECTURE §5), so a host incident may read it and name
  it as the root cause. Widening a host incident's scope to every container of the host would need an ACR.

## Design

- **Signals:** `host_disk_used_ratio_5m` (the worst declared mount, minimum over 5 minutes) and
  `host_disk_hours_to_full` (the soonest declared mount at its 15-minute fill rate; none when not growing).
- **Class `disk_pressure`** (host targets): matches at 90 % for 5 minutes; the findings give the ratio and, when
  growing, the time to full. RB-005 (branch RB-019). RB-005 metadata `detector: disk_pressure`, version bumped.
- **Alert `HostDiskPressure`:** every real filesystem (`ext4|xfs|btrfs`) by `argus_host`, not only `/`.
- **Lab:** `argus-lab-filler` (`sc05`): writes 2 MiB every 3 s until 92 %, then holds; no network; limits.
  Inventory `vm-166/container:argus-lab-filler`.

## Steps

1. **Code, tests first** (this branch).
2. **vm-166:** lab mount, deploy, node-exporter and host-probe recreated; the mount is seen (ratio about 0).
3. **SC-05 run on vm-166:** the filler to 92 %; the signal at 0.9 for 5 minutes; the alert firing; reset.
4. **Diagnosis** from vm-095 (with T-0022 step 5): DIAGNOSED, root cause the filler, no deletion proposed.
5. Brain, PR.

## Red seen / evidence

- **Step 1 (2026-10-08, code, tests first):** `tests/test_t0024_sc05_disk.py`, 15 tests.
  - **red:** 15/15 failed for the right reason (no disk signals, no `$mounts`, no mount validation, no
    `disk_pressure`, RB-005 metadata, the alert on `/` only, no `rslave`, no not-mounted refusal, no filler, no
    inventory entry, no mount script).
  - **green:** 15/15; full suite **207 passed, 7 skipped**. The scripted diagnosis first escalated: the filler was not
    in the host incident's scope; fixed with `depends_on: [vm-166/host:vm-166]` (the architecture's scope rule).
  - `promtool check rules` (5 rules) and both new PromQL expressions parse; `docker compose config` of the lab valid.
- **Steps 2-4 (2026-10-09, both VMs, mutating):** `b049086` on both hosts (vm-095 got the class and the inventory). The
  lab filesystem mounted (224 MiB ext4); node-exporter and the host-probe see it (not the root disk's numbers). The
  filler reached 92.6 %; `host_disk_used_ratio_5m` 0.926 and `HostDiskPressure` firing at 11:19:39; the scheduler
  pulled it and `inc_4d78232433a1` was **DIAGNOSED** (`disk_pressure`, root cause `argus-lab-filler`, every read on
  vm-166, no unscoped deletion advised). Reset: the lab filesystem back to 1 %, kept mounted. RB-005 1.0.2
  (`last_tested`). LAB BASELINE OK, NO INTERFERENCE on both
  ([evidence](../../execution/history/T-0024/step-02/evidence.md)). Observation: `hours_to_full` lags a stop by up to
  15 minutes (15-minute `deriv`).
