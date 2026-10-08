# RB-005 — Host disk almost full

## Metadata

```yaml
id: RB-005
title: Host disk almost full
status: draft
owner: Argus Team
version: 1.0.1
created: 2026-09-29
last_reviewed: 2026-10-08
source_review_date: 2026-09-29
last_tested: null
detector: disk_pressure
```

## Scope

Approved Linux filesystems backing Docker, logs or application storage on Host T. Record mount/device/namespace, filesystem type and Docker storage/log driver. Exclude device-latency-only incidents (RB-010); database-owned storage branches to RB-019. [Shared contracts](../RUNBOOK-CONVENTIONS.md) apply. Detector: `disk_pressure` (T-0023): a declared mount of the host target at 90 % or more for 5 minutes, with the time to full at the 15-minute fill rate.

## Incident definition

Writable byte or inode headroom is inadequate for expected growth, or writes already fail for capacity reasons. Distinguish available blocks for ordinary users from all free blocks, and inspect inode availability separately. [Linux statvfs](https://man7.org/linux/man-pages/man3/statvfs.3.html)

## User / service impact

Possible failed writes, broken logging, database interruption, deploy failure and loss of incident evidence. Identify the mount actually used by the failing workload; a full unrelated mount does not establish its impact.

## Trigger / detection conditions

Proposed detector/alert: relevant mount available bytes below 10% for 5 minutes, available inodes below 5%, or sustained positive growth predicting exhaustion within 1 hour; urgent on corroborated ENOSPC. Thresholds need per-filesystem calibration and a matching implemented detector before routing to Argus. Prediction is valid only over a representative growth window. Missing/read-only/unmounted filesystems are explicit states, not zero usage.

## Symptoms

ENOSPC, failed log/database writes, deployment errors, declining byte/inode availability; discrepancies between directory totals and filesystem allocation.

## Plausible causes / hypotheses

H1 image/build artifacts; H2 container/journal/application logs; H3 valuable application/database/volume growth; H4 many small files exhausting inodes; H5 deleted files still held open; H6 wrong mount, filesystem reservation/quota or read-only failure; H7 rapid current workload growth. Disk percentage alone identifies none of these.

## Required evidence

Mount identity, available bytes/inodes, slope and coverage, Docker categories including stopped containers/volumes, approved directory sizes with partial flag, logging configuration, open-deleted ownership and affected application's error. Do not add directory totals from overlapping paths or shared image layers as independent usage.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_disk_usage(path=None)` | Available/used bytes and inode headroom; allowed paths `/`, `/var/lib/docker`, `/var/log`, `/tmp` | `READ_ONLY_SAFE` |
| `get_disk_history(minutes=60)` | Root-filesystem history and linear time-to-full estimate only | `READ_ONLY_SAFE` |
| `get_directory_sizes(path)` | Bounded partial scan of allowlisted Docker/log/tmp directories | `READ_ONLY_SENSITIVE` |
| `get_docker_disk_usage()` | Images, writable layers, volumes and reclaimable cache | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Write errors and growth context | `READ_ONLY_SENSITIVE` |
| `get_container_status(container)` | Identity and available structured configuration | `READ_ONLY_SENSITIVE` |
| `clean_docker_cache(mode)` | Registered `build_cache` or `dangling_images` only; inspected gate closed | `MUTATING_HIGH_RISK` |

Directory `path` is a fixed enum, not arbitrary filesystem exploration. Its successful return may still be partial; never infer a complete ranking from a timed-out scan.

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_filesystem_history(mount_id, minutes)` with bytes/inodes/source times; `get_open_deleted_files(mount_id, limit)` with owner, bytes and no content; `get_log_storage_usage(service_id)` with container/journal/application category, logging driver and rotation policy; `get_filesystem_constraints(mount_id)` for quotas/read-only state. The first is `READ_ONLY_SAFE`; ownership/configuration reads are `READ_ONLY_SENSITIVE`. Use approved mount IDs, not arbitrary paths.

**MISSING TOOL REQUIREMENT:** a cleanup preview/commit contract bound to reclaimable object IDs, minimum age, retained rollback images and maximum reclaim budget. Existing `clean_docker_cache(mode)` does not express all these bounds.

## Diagnostic workflow

| Step | Action / reason | Interpret / next step |
|---|---|---|
| 1 | Disk usage plus failing-write context | Bind actual mount; bytes healthy/inodes low → H4. Read-only/permission error → H6, do not prune. |
| 2 | Correct mount's history | Estimate time-to-full only with positive stable growth and coverage. Root-only history cannot explain a separate data disk. Immediate exhaustion → owner escalation while collecting bounded evidence. |
| 3 | Docker usage and allowlisted directory sizes | Cache/images → potential H1; logs → H2; volume/data → H3. Partial scans leave attribution incomplete. |
| 4 | Compare filesystem allocation with visible named files | Large unexplained difference → H5/reservations/mount layering; request open-deleted/constraint tools rather than more deletion. |
| 5 | Confirm owner/retention and ongoing growth | Valuable/unknown data → protect and escalate. Reclaimable cache with accepted preview/policy → one HITL cleanup candidate; otherwise operator intervention. |
| 6 | Capture before-state, act only through approved procedure, verify same mount | Freed space on another filesystem does not satisfy recovery. |

## Decision tree

```text
write capacity failure on identified mount?
  bytes low -> attributable cache / logs / valuable data / unexplained allocation
  inodes low -> bounded small-file ownership investigation
  neither -> quotas / read-only / permissions / wrong mount
reclaimable objects + enforced preview + policy? -> HITL bounded cleanup
unknown/protected data or missing evidence? -> no deletion; escalate
```

## Evidence interpretation

Removing a pathname does not free an open file's storage until references are released. Investigate the owning process instead of repeating unlink operations. [Linux unlink](https://man7.org/linux/man-pages/man2/unlink.2.html)

Build cache cleanup is a distinct operation; broad system prune also targets other object classes and is inappropriate as a default diagnostic action. [Docker builder prune](https://docs.docker.com/reference/cli/docker/builder/prune/), [system prune](https://docs.docker.com/reference/cli/docker/system/prune/)

## False positives and edge cases

Bind/overlay mounts, reserved blocks, inode exhaustion with free bytes, sparse files, deleted-open files, Docker sharing, quota limits, a disappearing mount, canceled scan and one-time build growth. A linear prediction is not a deadline guarantee.

## Diagnosis outcome

All five common outcomes are allowed. Probable cause identifies mount, owner/category, allocation and growth evidence, with competing explanations considered. Unknown owner or partial scan supports `insufficient_evidence`, not arbitrary cleanup.

## Mitigation

Operator pauses a proven non-critical producer or expands capacity through a reviewed procedure. Narrow cache cleanup is optional only after separate release of its missing bounds. Preserve enough space for audit/evidence; do not fill the affected disk with snapshots.

## Recovery

Same mount has sufficient byte/inode reserve, affected service resumes expected operations, and current growth is controlled. Reclaiming space while the source keeps filling it is temporary relief.

## Root-cause correction

Configure retention/rotation, fix excessive logging, bound artifact retention or resize/migrate legitimate data. For Docker JSON logging, configure rotation through supported driver options; daemon defaults do not retroactively reconfigure existing containers. Never edit Docker-managed log files directly. [Docker JSON-file logging](https://docs.docker.com/engine/logging/drivers/json-file/)

## Action safety

Cleanup is `MUTATING_HIGH_RISK`: exact approved host, enum mode, immutable preview, reclaimable-only objects, retention/rollback-image protection, no volumes, fixed budget, fresh revalidation and one execution. Blast radius includes future builds/deploy rollback. Block unknown ownership, missing preview bounds, active references, insufficient benefit, ongoing uncontrolled growth or closed gate. Operator log rotation/capacity changes need exact service/mount, retention/backup plan and separate approval; no generic model filesystem action exists.

## Human-in-the-Loop

Show predicted relief on the actual mount, selected objects, irreversible deletion, retained rollback assets, growth estimate and recovery target. Approval of a cache mode does not authorize deleting logs or volumes. Current production restart-only profile blocks cleanup.

## Forbidden actions

`FORBIDDEN`: unrestricted `docker system prune`, volume deletion, arbitrary `rm`/truncate, removing database/WAL files, editing Docker logs, restarting Docker blindly, deleting unknown data or increasing scan scope to arbitrary paths.

## Evidence preservation

Save compact mount/usage/category/owner summaries remotely or to a healthy approved evidence sink. Preserve a bounded redacted sample and retention decision before log operations; snapshot failure under disk pressure is explicitly recorded and escalated.

## Verification

Three source-fresh observations of the same mount after action, then a 15-minute growth window. Proposed recovery reserve: at least 15% bytes and 10% inodes, or the larger service-specific operating reserve; time-to-full must no longer breach policy. Confirm real service operations and no renewed ENOSPC. Fast regrowth, wrong-mount relief, stale data or missing write-health evidence fails verification. Do not claim sustained recovery if timeout is shorter than this window.

## Rollback

Deleted cache/log data has no automatic undo. Rebuilding cache may consume time/storage and is not a recovery guarantee. Configuration changes retain previous settings; owner rollback must not re-enable unbounded growth. Volume/data restoration belongs to a tested backup procedure, never this cleanup path.

## Escalation

Platform/storage owner for unknown allocation, quotas, open-deleted files or impending exhaustion; DBA for database paths. Attach mount identity, time-to-full uncertainty, ownership/partial-scan evidence, protected resources and action result. Stop any repeat cleanup after insufficient recovery.

## Recording / memory

Common record plus mount/device identity, reclaimed versus predicted space, deletion preview, retention decision, inode trend, producer state and growth follow-up.

## Prevention / follow-up

Per-mount/inode alerts; rotation and artifact budgets; retained deployment rollback set; mount-aware history; safe cleanup dry-runs; capacity forecasts tied to workload.

## Lab validation

Use a disposable 256 MiB test filesystem inside a snapshot-restorable VM, never the workstation/root filesystem. Operator pre-fills it to 85% with one named synthetic fixture, then writes synthetic logs at 1 MiB/s with a hard stop at 95% and 120-second writer watchdog. Retain the bounded allocation through the configured lab detection window. Separately create small files until its configured inode reserve crosses threshold; separately hold a deleted synthetic file open. Expect proposed disk trigger (currently unsupported), RB-005 diagnosis distinguishing H2/H4/H5, and zero broad prune calls. Deny deletion of a protected volume fixture; absent preview capability blocks agent cleanup. Operator removes only known fixtures/releases the test handle; verify same-mount bytes/inodes and service writes for 15 minutes and record all lifecycle stages. Restore snapshot on abort. No fault injection was run.

## References

- [Linux statvfs](https://man7.org/linux/man-pages/man3/statvfs.3.html), [unlink](https://man7.org/linux/man-pages/man2/unlink.2.html).
- [Docker builder prune](https://docs.docker.com/reference/cli/docker/builder/prune/), [system prune](https://docs.docker.com/reference/cli/docker/system/prune/), [JSON-file logging](https://docs.docker.com/engine/logging/drivers/json-file/).
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — root-only history and closed cleanup gate.

## Argus capability gaps

### Missing telemetry

Per-mount history, constraints, log-category/retention inventory and open-deleted ownership.

### Missing tools

`get_filesystem_history`, `get_open_deleted_files`, `get_log_storage_usage`, `get_filesystem_constraints`, bounded cleanup preview/commit.

### Tool improvements

Mount/namespace identity, preserve partial scan flags, distinguish user-available bytes, deterministic reclaimability/retention/budget enforcement.

### Detector improvements

Implement filesystem/inode/growth detector and matching alerts; current architecture has no disk incident class.
