## 2026-10-25 — T-0049 R1: docker disk replay fixtures

Type: code (offline; no class offer)
Who: juanbetancurm (+ agent)
Context: R1 offers a read to a class only after a measured batch. `docker.disk_usage` calls `/docker/df`, but the
eight labelled `disk-*` cases had no such fixture, so replay failed before the read could be measured.
Decision / result:
- Added a `/docker/df` fixture to all eight disk cases in the real executor shape: images, containers and volumes
  counts and bytes, build cache bytes and collection time. Labels are unchanged and no class was edited.
- Host-wide totals exclude the lab-fill bind mount. The stopped-container count is 1 only in the two stopped cases
  and 0 in the other six, as each case's container status says.
- Added `tests/test_t0049_docker_disk_replay.py`: every case replays through the real `docker.disk_usage` and returns
  exactly the executor fields with non-negative integer counts and a valid collection time.
Consequences: Replays are complete, but disk use is host-wide and carries no per-container ownership. It tells apart
a stopped container (stopped count) and nothing else; it cannot tell a growing fill from a full, idle one, a
read-only mount, a missing log, or another writer on the root volume. Logs, mounts and file-system reads do that.
The lab-fill bind mount being excluded from the totals is an assumption, not a recorded observation. The fixtures are
only proven to parse through the real read (the replay test calls it directly); no baseline run consumes them yet,
because `docker_disk` is offered to no class. Expected gain from offering this read to the disk class is low; no class
offer was made.

### Test state

- Red first: with the fixtures reverted, the replay test failed with `/docker/df: not found`.
- With the fixtures, the replay test (it globs every `disk-*` case) passes on the branch at current main (`106190b`).
- The replay, T-0037 and evaluation tests passed together (122); Ruff, Brain lint/audit and `split_entry` were clean.

### Next step

Commit, push the branch and open the PR; conantkd reviews. A later measured batch decides whether the disk class is
offered `docker.disk_usage`.
