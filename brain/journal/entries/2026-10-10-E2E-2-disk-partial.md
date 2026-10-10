## 2026-10-10 — E2E-2 follow-up: an unmounted disk is a stated fact, not a failed read (E2E-2)

Type: implementation
Who: conantkd (+ agent)
Context: #70's review. Without a mount `host.disk_usage` reads every declared mount, but one 409 from the host-probe
(the lab filesystem not mounted) failed the whole read, so the model would also lose `/`.
Decision / result: a mount that cannot be read is reported as `unavailable (<reason>)` and the others are still read;
the read fails only when every mount fails; an explicit mount fails as before; `source_time` is the oldest read. 4
tests (red seen 2/4). No VM step of its own: it ships with E2E-2's step 2 rebuild.
Consequences: SC-05's re-run is unaffected while the lab filesystem is mounted; when it is removed, the model still
sees the root disk and is told the lab mount is missing.
References: [`../../tasks/current/E2E-2-evidence-gaps.md`](../../tasks/current/E2E-2-evidence-gaps.md).

### Test state

**E2E-2 follow-up (2026-10-10, `task/E2E-2-disk-partial`):** 4 more tests in `tests/test_e2e2_evidence_gaps.py` (12
in all), red seen 2/4; the offline suite passes.
