# Open problems and pending team decisions

When a problem is fixed, set its status to `fixed` with the date, and add a journal entry if it is significant.
**Status:** `open` · `in progress` · `fixed` · `dropped` (with reason) · decisions: `pending` · `decided`

| ID | Item | Status | Opened |
|---|---|---|---|
| **D-001** | Cross-host path and alert direction: architecture text vs the running system | **decided** 2026-10-08 (`conantkd`): option B as transport profiles, [ACR-0003](architecture/changes/ACR-0003-transport-profiles.md); second approval in the T-0022 PR | 2026-10-02 |
| **D-002** | Move the runbook library into this repository (the architecture expects it there) | **decided and done** 2026-10-02 | 2026-10-02 |
| OP-001 | Runbook `detector` metadata uses old or empty class names | fixed 2026-10-09 on `task/OP-001-runbook-detectors` (review pending) | 2026-09-30 |
| OP-002 | P0 safety gaps of the runbook library not yet reconciled with architecture v1.8 | open | 2026-09-30 |
| OP-003 | Runbook safety classes not mapped to `CapabilitySpec.risk` | open | 2026-09-30 |
| OP-004 | LangGraph checkpoints grow forever; checkpoints of failed runs are orphaned | accepted 2026-10-05 — to implement | 2026-10-05 |
| **OP-005** | The `restarts_10m` signal undercounts restarts of a container younger than its window | **fixed** 2026-10-09 — verified on both VMs (PR #41) | 2026-10-05 |
| OP-006 | LangGraph `recursion_limit` is fixed at 100 and can be too small for larger step budgets | fixed 2026-10-05 | 2026-10-05 |
| **OP-007** | A dependency probe disappears while its owner is restarting, hiding the cause of a crash loop | fixed 2026-10-07 (`owner_active`: running or restarting; deployed on vm-166) | 2026-10-07 |
| **OP-008** | Postgres backups are never rotated, and the backup's consistency check will stop once the scheduler writes often | in progress — offline implementation and Docker tests pass; VM dry run and approved apply pending | 2026-10-07 |
| OP-009 | A worker that loses its lease keeps running the incident; with two workers the same run could execute twice | fixed 2026-10-08 (`task/OP-009-lease-loss`: the renewer retries, a lost claim cancels the run) | 2026-10-08 |
| OP-010 | The db-probe cannot connect when every usable slot is taken, so `postgresql_connection_exhaustion` cannot fire at 100 % | **fixed** 2026-10-09 — SC-04 at 100 % DIAGNOSED from the pulled alert | 2026-10-08 |
| OP-011 | Two alerts on one target open two incidents: §6.4 correlation is not implemented | open | 2026-10-09 |

---

## D-001 — Cross-host path and alert direction (decided by ACR-0003)

**Status:** decided 2026-10-08 by `conantkd` — option B, generalized as **transport profiles**
([ACR-0003](architecture/changes/ACR-0003-transport-profiles.md)): this deployment is `restricted-ssh` and pulls alerts
from an Argus-owned Alertmanager; the second team approval (`juanbetancurm`) is given in the T-0022 PR ·
**Opened:** 2026-10-02 · **Decided by:** the whole team (including `conantkd`)

**The difference.** Architecture §3.6 (reference values) says the two hosts talk over the **private network with no
tunnel**, and that alerts are **pushed** (Alertmanager on vm-166 → webhook on vm-095). The running system uses a
**restricted SSH tunnel** over port 22 (the only port open between the VMs) and **pulls** alerts through it
(`ReconcileFiringAlerts`), because the cloud network rules cannot be changed by the team.

**Options.**
- **A. Keep the architecture text; change the deployment later.** If someone with access to the cloud console opens
  the needed ports between the private addresses, switch to the private network and push alerts. Only the inventory
  URLs, the compose port bindings and the alert route change; the tunnel is removed.
- **B. Change the architecture to match the running system** through an ACR (§3.6: SSH tunnel, pulled alerts).
- **C. Use the existing WireGuard tunnel** — only with `conantkd`'s agreement, since it belongs to the protected
  deployment.

**Until decided:** the running system stays as it is (tunnel + pull). Nobody changes the architecture text or the
transport alone.

**Done when.** The team has chosen; the result is either an accepted ACR (B) or a planned task (A or C), recorded in
the journal.

---

## D-002 — Move the runbook library into this repository

**Status:** decided and done (2026-10-02, owner: deploy keys are disabled in the organization, so CI could not read
the separate repository; moving the library removes the need) · **Opened:** 2026-10-02

**The difference.** Architecture §2.4 places the runbooks in the code repository (`argus/runbooks/`, "reviewed copy
of the runbook library v1.1.0" + `RUNBOOK-CONVENTIONS.md`). The running system reads them from a separate private
repository (`agenticteam03/runbooks`, pinned in `config/runbooks.lock`). That came from an implementation choice on
2026-09-30 ("read in place, never copied") and the shared-Brain plan decision D2, not from the architecture. It costs
a deploy key for CI, a deploy key per VM, and a pin bump plus a second repository for every runbook change.

**Done.** Moved (without history: the old repository keeps it; provenance in `argus/runbooks/README.md`) the reviewed runbooks (RB-001…RB-021, `RUNBOOK-CONVENTIONS.md`, `RUNBOOK-INDEX.md`) into
`argus/runbooks/` with their history (`git subtree`), keep each runbook's own `version` in its metadata (already
recorded in the recall audit), deploy them with the code, retire `config/runbooks.lock` and the CI deploy key, and
leave the research material (books, assessments, gap backlog) in the old repository as history. OP-001 is then fixed
in this repository.

**Alternative.** Keep the separate repository (works today; costs as above).

**Done when.** Decided; if yes, done as one task (tests: recall finds every class's runbooks from `argus/runbooks/`;
deployment no longer mounts `/opt/argus-runbooks`) and the journal records it.

---

## OP-001 — Runbook `detector` metadata uses old or empty class names

**Status:** fixed 2026-10-09 on `task/OP-001-runbook-detectors` (review pending) · **Opened:** 2026-09-30

**Problem.** Each runbook in the library (`argus/runbooks/RB-*.md`) has a `detector:` field. The original corpus used
v1.7 names or left the field empty: RB-001 had `oom_restart_loop` (v1.8: `container_restart_loop`, shared with RB-008),
and many later runbooks had `null`. Architecture §15.3 requires that "a runbook's `detector` metadata names the class
that uses it".

**Fix.** Set `detector:` in every runbook to its v1.8 class (§1.3), bump `version` and `last_reviewed` on changed
runbooks, and update `RUNBOOK-INDEX.md`. The metadata-only library revision is v1.1.1. This does not enable draft
classes or promote untested runbooks.

**Done when.** All 21 runbooks name a class that exists in §1.3, and a check shows no class without a runbook and no
runbook without a class.

**Verification.** `tests/test_runbook_detector_metadata.py` compares the 21 metadata fields and index rows with the
20 classes and their primary runbooks in architecture §1.3. The test was red before the edits and is green afterward.

---

## OP-002 — P0 safety gaps not yet reconciled with architecture v1.8

**Status:** open · **Opened:** 2026-09-30

**Problem.** The library's `ARGUS-CAPABILITY-GAPS.md` lists eight **P0** gaps written against an older code base.
Each must be settled in the architecture (ACR) before the related implementation. First assessment — to be verified:

| Gap | Asks for | Against v1.8 | Likely change |
|---|---|---|---|
| G-001 Deployment profiles | named, versioned profiles (production / lab); missing profile fails closed | partial: per-(capability, target) write gate, no profile | `profile` in the policy file; write gate evaluated per profile |
| G-002 Typed prerequisites | preconditions as typed predicates on fresh, identity-bound evidence | **missing**: §13.1 uses free-text `preconditions` | typed predicates evaluated at `propose_action` and `precheck_action` |
| G-003 Observation provenance | source vs collection time, coverage, units, partial state, identities | partial | add the fields to `Observation` / `EvidenceRecord`; missing is never zero or healthy |
| G-004 Approval binding | immutable proposal bound to what it acts on, previews | mostly covered | extend `identity()`; preview in the approval view |
| G-005 Verification windows | stability windows, provisional vs final recovery | partial | `stability_window` per class; provisional/final states |
| G-006 Data minimization | per-source field allowlists, literal redaction | partial | `allowed_fields` per `CapabilitySpec` |
| G-007 Helper semantics | missing/partial data never becomes healthy or root cause | principle missing (implemented for metrics freshness) | state the rule in §12.3; contract fixtures |
| G-008 Corpus/dispatcher separation | runbook IDs from metadata, bounded passages, tools never from runbook text | covered by §15.3 | verify that writes are offered only for registered classes |

**Done when.** Each gap is covered, changed through an ACR, or dropped with a reason.

---

## OP-003 — Runbook safety classes not mapped to `CapabilitySpec.risk`

**Status:** open · **Opened:** 2026-09-30

**Problem.** The library's conventions classify operations as `READ_ONLY_SAFE`, `READ_ONLY_SENSITIVE`,
`MUTATING_LOW_RISK`, `MUTATING_HIGH_RISK`, `FORBIDDEN`; architecture §12.3 uses `risk: low | medium | high | very_high`
plus `permission: read | write_hitl`. They do not map cleanly (sensitive reads need allowlists; `FORBIDDEN` has no
equivalent).

**Fix (to discuss, ACR).** Adopt the five classes as `safety_class`, derive `permission` from it; sensitive reads get
mandatory field allowlists (ties to G-006); `FORBIDDEN` operations are never registered; classify every capability in §12.2.

**Done when.** §12.3 has one scheme; every capability has a class; policy and redaction rules refer to it.

---

## OP-004 — Checkpoint retention (accepted, to implement)

**Status:** accepted 2026-10-05 (PR #7, approved by `conantkd`) · **Opened:** 2026-10-05 · **Found by:** `conantkd` (T-0013 review)

**Problem.** Since T-0013 every investigation leaves rows in `checkpoints`, `checkpoint_blobs` and `checkpoint_writes`,
and nothing ever removes them: the runtime role has no DELETE (on purpose, migration 002). A run that ends with an
exception leaves a pending checkpoint that is never resumed, because its incident is already final. Small today, but
it grows without limit.

**Proposed solution — an automatic cleanup policy:**
- a small script `ops/checkpoint-retention.sh` on vm-095, run **as the owner role** inside the Postgres container
  (the runtime role keeps "no DELETE anywhere"), once a day by a systemd timer (later by the Argus scheduler);
- it deletes the checkpoint rows (all three tables) of threads whose incident is final (`closed` or `escalated`) and
  ended more than **30 days** ago (configurable: `ARGUS_CHECKPOINT_RETENTION_DAYS`); a final incident's checkpoints
  are never needed again, because a final incident is never resumed;
- the same rule removes the orphaned checkpoints of failed runs (their incident is final too);
- it never touches incidents, evidence, audit or run events (they stay insert-only), and it records each run as an
  audit row `maintenance.checkpoints_pruned` with the number of threads removed;
- `argus db check` keeps proving that the runtime role cannot delete checkpoints.

**Alternatives.** Keep everything (disk grows; fine for months at today's volume) · delete at the end of every run
(loses the record of how a run progressed, and needs DELETE for the runtime role — rejected).

**Done when.** Approved here; then a task implements the script, its Postgres test (old final threads removed, recent
and non-final ones kept, evidence and audit untouched) and the timer on vm-095, with NO INTERFERENCE.

**Review conditions (conantkd, PR #7) — part of the accepted proposal:**
1. Implement it as an Argus command (for example `argus db prune-checkpoints`) run with the owner DSN, not as a
   standalone SQL/bash script: the audit row is then written by the same code and in the same format as every other
   audit row, and the Postgres tests can cover it. The systemd timer (named `argus-v18-*`) only calls that command.
2. Dry-run first: the command reports what it would delete without deleting; the first runs on vm-095 are dry-runs.
   Deleting database rows is a stop condition (`agents/AGENT_PROTOCOL.md` §6) and the Postgres backup/restore drill
   is not done yet.
3. The `incident` table has no end-time column: "ended" means `body->>'closed_at'` (set when the incident becomes
   final); an incident without it is never pruned.

---

## OP-005 — `restarts_10m` undercounts young containers (fixed)

**Status:** fixed 2026-10-09 (`task/OP-005-young-restarts`, PR #41; VM proof in
[`execution/history/OP-005/step-02/`](execution/history/OP-005/step-02/evidence.md); design
accepted 2026-10-06 in PR #8) · **Opened:** 2026-10-05 ·
**Found by:** `conantkd` (T-0013 review) · **Approval:** this PR (re-review by `conantkd`)

**Problem.** `config/signals.yaml` computes `restarts_10m` as `max_over_time(count[10m]) - min_over_time(count[10m])`.
For a container that has existed for less than 10 minutes, the first sample Prometheus has is often already above 0
(the container restarted before the first scrape, every 15 s), and those restarts are lost. Observed in T-0013 step 5:
Docker counted 3 restarts while the signal said 1 (first run) and 2 (the reviewer's run), so the restart-loop class
(threshold 3) did not match and SC-01 was escalated as unsupported until enough time passed. The observed metric did
not match what really happened.

**Why the first version was rejected (`conantkd`, PR #8).** It used `count - (count offset 10m or count * 0)`. "No
sample 10 minutes ago" does not mean "the container is new": it also happens when the exporter or Prometheus was down
at that time (a redeploy, a scrape gap longer than the 5-minute lookback) or when a container was just added to the
exporter's list. An old container with 5 restarts from last week would then show 5 ≥ 3 and open a **false
restart-loop incident**. An undercount delays a diagnosis; an overcount invents an incident.

**Proposed solution (`conantkd`'s design).**
1. The exporter (`services/target/service.py`) also publishes the container's creation time from `docker inspect`
   (`.Created`): `argus_container_created_seconds{container="..."}` in Unix seconds. An absent container has no
   series, as today.
2. The signal counts all restarts only for a container that is really young:

```text
restarts_10m = clamp_min(
    (count and on(argus_host, container) (time() - created < 600))
  or on(argus_host, container)
    (count - count offset 10m),
  0)
where count   = argus_container_restart_count{argus_host="$host",container="$name"}
      created = argus_container_created_seconds{argus_host="$host",container="$name"}
```

| Case | Value |
|---|---|
| container created less than 10 minutes ago | all its restarts, the same as Docker's counter (the T-0013 step-5 case) |
| older container, series present 10 minutes ago | the restarts of the last 10 minutes |
| older container, gap at `t - 10m` (exporter or Prometheus down, newly added) | **no value**: the signal is unknown, not zero and not inflated (G-007, "unknown ≠ healthy") |
| creation time not published (exporter not yet redeployed) | the difference only; never inflated |

**One refinement for the re-review: the order of the two branches.** The review text puts the difference first and
the young-container branch after `or`. With that order, a container that is **removed and recreated under the same
name** within 10 minutes (SC-01 does this with `compose rm` / `up`) still has an old sample at `t - 10m`, so the
difference wins: `new count − old count`, clamped to 0, which is the original undercount. Putting the
young-container branch first gives the counter since creation. Both branches use explicit `on(argus_host,
container)` matching, so the metric name cannot keep `or` from matching.

The S5.6 readiness gate in the T-0013 `code.bash` uses the same expression and changes with it.

**Tests (requested in the review).**
- young container (created 3 minutes ago, Docker counter 3) → 3;
- **old container + scrape gap at `t - 10m`** (counter 5, no sample then) → no value (not 5, not 0);
- old container without a gap, 2 restarts in the last 10 minutes → 2;
- recreated container (same name, created 2 minutes ago, old series 5 at `t - 10m`, new counter 3) → 3;
- the exporter publishes `argus_container_created_seconds` from `.Created` (unit test of its output);
- `config/signals.yaml` holds exactly the approved expression.

The PromQL cases run against synthetic series (`promtool test rules` with a recording rule of the same expression,
or a throwaway Prometheus in CI). The implementing task chooses which.

**Alternatives.** Wait longer before diagnosing (a workaround, not a fix: the value stays wrong) · the first version
above (rejected: false positives after scrape gaps) · let the exporter publish restarts-since-creation directly
(moves the logic out of the signal catalogue, where every signal lives).

**Done when.** `conantkd` approves this revision. Then a task changes the exporter and `config/signals.yaml` with
the tests above, redeploys the exporter on both VMs, and verifies on vm-166:
- SC-01 right after the third restart: the signal shows 3, the same as Docker, and SC-01 is diagnosed without extra
  waiting;
- after an exporter restart, a healthy old container shows no restart loop.

---

## OP-006 — LangGraph `recursion_limit` is fixed at 100 and can be too small for larger step budgets

**Status:** fixed 2026-10-05 (`GraphRunner.recursion_limit`, tests `test_recursion_limit_is_100_with_the_default_budgets`
and `test_a_large_budget_ends_escalated_not_with_a_recursion_error`, red seen) · **Opened:** 2026-10-05 (T-0013 review, conantkd)

**Problem.** `GraphRunner.run` passes `recursion_limit: 100` to LangGraph (`argus/orchestration/graph_runner.py`).
Since the T-0013 review fix, `act` and `evidence_pack` make one read per graph step, so one investigation round costs
`1 + reads` graph steps instead of 2. The worst case is `max_steps × (1 + max(ARGUS_MAX_READS_PER_STEP, 6)) + 4`
(6 = the largest deterministic plan, the evidence pack, which the model's read limit does not cap). With the defaults
(8 steps) it is 60, below 100. With `ARGUS_MAX_STEPS=20` it is 144: the run would stop with `GraphRecursionError`
although Argus is still inside its own budget.

The round budget is not chosen by the model: `recall` sets it to `min(class max_steps, ARGUS_MAX_STEPS)` and
`investigate` only counts it. An infinite loop is still impossible as long as the limit is a fixed number.

**Fix (agreed in review).** `recursion_limit = max(100, max_steps_cap × (1 + max(max_reads_per_step, largest plan)) + 4 + 10)`:
unchanged (100) with today's configuration, grows only when the budgets need it. Tests: the default limit is 100; with
20 steps × 5 reads a model that exhausts the budget ends `escalated`, not with `GraphRecursionError` (red first).
Separate, optional: refuse to start when `ARGUS_MAX_STEPS` is above a sane ceiling (for example 30), so a typo cannot
create a huge budget (cost of model calls and reads).

**Done when.** The limit is derived from the budgets, both tests pass, and this item is set to `fixed`.

---

## OP-007 — A dependency probe disappears while its owner is restarting

**Status:** fixed 2026-10-07; code on `task/op-007-restarting-probe-fix` (analysis confirmed by `conantkd`: in a crash loop Docker
reports `State.Restarting` during the back-off wait, so most 10-second samples dropped the probe; test
`test_exporter_keeps_the_probe_of_an_owner_in_a_restart_loop`, red seen); deployed on vm-166 (`9c04e90`,
[evidence](execution/history/OP-007/step-01/evidence.md)) · **Opened:** 2026-10-07 · **Found by:** `juanbetancurm` (review of PR #27, T-0018) ·
**Fix with:** its own small task (`task/op-007-restarting-probe-fix`), independent of T-0019

**Problem.** T-0018 changed `probe_lines` in `services/target/service.py`: a dependency probe is published only
while its owner container is `running`. The reason is good: the SC-07 client exists only during its scenario, and
its probe (client → backend on the wrong network) would otherwise fail all the time and keep
`DependencyProbeFailed` firing for a container that is not there.

But "not running" also covers an owner that crashes and restarts **because** its dependency is down, a common
pattern (an app that exits at startup when it cannot reach its cache or database). In the lab, `argus-lab-api`
probes `argus-lab-cache`. While the owner restarts, its probe disappears, so `dependency_unavailable` loses the
signal that names the real cause at exactly the moment it matters. The incident would look like a plain restart loop.

**Proposed fix.** Publish the probe when the owner is `running` **or restarting** (Docker `State.Restarting`, or a
recent restart). Keep skipping owners that are missing or exited by design. That still removes the SC-07 false alarm.

**Test (red first).** In `tests/test_sc07_network.py` or a new test: an owner in a restart loop keeps its probe line
(`argus_probe_success ... 0`); an absent owner still has none.

**Done when.** The probe survives an owner's restart loop, the SC-07 false alarm stays fixed, the target service is
redeployed on vm-166, and this item is set to `fixed`.

---

## OP-008 — Backup retention, and a consistency check that survives a busy database

**Status:** in progress 2026-10-09 (`task/OP-008-backup-retention`; offline implementation verified, VM dry run and
approved apply pending); proposal accepted 2026-10-07 (PR #31, approved by `juanbetancurm`; snapshot approach,
scheduling decided later) · **Opened:** 2026-10-07 · **Found by:** `juanbetancurm` (after-merge review
of PR #25, T-0017) · **Proposal by:** `conantkd` (+ agent) · **Fix with:** its own task, with or after T-0014
(scheduler)

**Problem 1 — no retention.** Every `ops/db-backup.sh backup` leaves `argus-<UTC>.dump` (+ `.dump.sha256`,
`.fingerprint`) in `/opt/argus-v18/backups`, and nothing removes them. Harmless while backups are manual; once they
are scheduled the folder grows without limit.

**Problem 2 — the check assumes a quiet database.** `backup` fingerprints every table (rows and a content hash)
before and after `pg_dump` and discards the dump when they differ. Today the database is quiet, so they match. Once
the T-0014 worker and scheduler write often, they will rarely match and the backup will end `BACKUP STOP`, although
`pg_dump` itself is consistent (it reads one snapshot).

**Proposed fix.**

1. **One snapshot for the fingerprint and the dump (general; no quiet window).** Open a session on the live database
   with `BEGIN ISOLATION LEVEL REPEATABLE READ; SELECT pg_export_snapshot();`, compute the fingerprint inside that
   session, and run `pg_dump --snapshot=<id>` while it stays open; then end the session. The fingerprint and the dump
   see exactly the same data however busy the database is, so `verify` keeps comparing the restored copy against it
   as today. Cost: the script keeps a `psql` session open in the background (a coprocess or a FIFO) during the dump.
   The live database is still only read.
2. **Retention: `db-backup.sh prune --as <handle> [--apply]`.**
   - Dry-run by default: it lists what it would delete; `--apply` deletes. Deleting backups is a stop condition
     (`agents/AGENT_PROTOCOL.md` §6), so the first runs on vm-095 are dry-runs (the same rule as OP-004).
   - Keeps the newest N backups (`ARGUS_BACKUP_KEEP`, default 7) and **never deletes the newest verified one**, even
     if it is older than the N kept.
   - `verify` writes `<base>.verified` after `VERIFY OK`, so `prune` knows which backups are proven restorable.
   - Deletes all the files of one backup together (`.dump`, `.dump.sha256`, `.fingerprint`, `.verified`), never a
     dump alone.
3. **Scheduling (decision for the team, not part of this fix).** The script refuses to run unless
   `/opt/argus-v18/SESSION` is the caller's, and a timer has no session. A scheduled backup needs an explicit mode
   (for example `--as scheduler`) accepted only for `backup` and `verify` (they only read the live database);
   `prune --apply` keeps requiring a person. This changes who may operate the VMs, so the team decides it with T-0014.

**Alternative to 1.** A quiet window: pause the worker and scheduler during the backup. Simpler, but it stops Argus and
depends on how T-0014 is built.

**Tests (red first).** A database written to during the dump still ends `BACKUP OK`, and `verify` of that dump ends
`VERIFY OK` (real Postgres, `ARGUS_TEST_DOCKER=1`); `prune` dry-run deletes nothing; `prune --apply` keeps the newest
N and the newest verified one, and removes every file of a pruned backup; `verify` writes `.verified` only on success.

**Done when.** The team accepts this proposal (or the alternative); then a task implements 1 and 2 with the tests
above, runs `prune` as a dry-run on vm-095 first, and sets this item to `fixed`.

**Implementation progress (2026-10-09).** `ops/db-backup.sh` now fingerprints in a read-only exported snapshot and
passes that snapshot to `pg_dump`; `verify` writes `.verified` only after a matching restore. `prune` previews by
default, retains the newest N and the newest verified set, and removes complete older sets only with `--apply` and
the VM lease. Fifteen offline/local-Docker tests pass, including a live write between export and dump. No VM backup
was pruned; see [the task](tasks/current/OP-008-backup-retention.md).

---

## OP-009 — A worker that loses its lease keeps running the incident

**Status:** fixed 2026-10-08 on `task/OP-009-lease-loss` (tests `tests/test_op009_lease_loss.py`, red seen; see
**Fix** below) · **Opened:** 2026-10-08 · **Found by:** `conantkd` (+ agent), after-merge review of PR #33 (T-0014) ·
**Fix with:** its own small task, **before a second worker is ever started** (today vm-095 runs one)

**Problem.** In `argus/infrastructure/worker.py`, `_renew` extends the claim every `lease_s / 3`. Two cases leave a live
run without a lease:

1. `renew_claim` returns False (the claim is no longer this worker's): the renewer logs and stops, but
   `runner.run` keeps going (the `renew_claim` docstring says the worker "must stop").
2. `renew_claim` raises (for example a transient database error): the exception ends the renewer thread silently;
   the lease then expires in the middle of the run.

With one worker nothing happens: `recover()` runs only between runs. With two or more, another worker would requeue
and resume the same incident from its checkpoint while the first one still writes to it: duplicate model calls and
evidence, and a race on the final status.

**Also (minor).** In Postgres the claim uses the database clock (`now()`), while `renew_claim` and `requeue_expired`
pass the worker's `utcnow()`. Same host today; using `now()` in all three keeps one clock.

**Proposed fix.** `_renew` catches exceptions and retries until the lease has really expired; on a lost claim it sets a
flag that the graph runner checks between nodes (cooperative cancel: stop at the next node, record
`incident.claim_lost`, write nothing more).

**Tests (red first).** A store whose `renew_claim` raises once and then succeeds: the run keeps its lease. A store whose
`renew_claim` returns False: the run stops at the next node and writes no final status.

**Done when.** Both tests pass, and this item is set to `fixed`.

**Fix (2026-10-08, `conantkd` + agent).**
- `argus/infrastructure/worker.py`: `_renew` retries a failed renewal while the lease lasts; a lost claim
  (`renew_claim` False, or the lease expired while retrying) sets a `lost` event that the worker passes to the runner
  (`runner.run(id, cancel=lost)`).
- `argus/orchestration/runner.py`: `ClaimLost`; the cancel signal is a context variable per run. `_guard` runs before
  every investigation step, before every read and before `_record`. A lost claim audits `incident.claim_lost` and
  writes no final status; a crash while the claim is lost records nothing either.
- `argus/orchestration/graph_runner.py`: every graph node starts with the guard, so the checkpoint stays at the last
  completed node and the new owner resumes from it (`incident.resumed`).
- Postgres: `renew_claim` and `requeue_expired` use the database clock (`now()`) unless a test passes `now`.
- Tests: 7 in `tests/test_op009_lease_loss.py` (red: `run()` had no `cancel`; the renewer died at the first error;
  a lost claim did not cancel), and `test_worker_lease_uses_the_database_clock` (Postgres, a refactor: green from the
  start). The runner test doubles in `test_worker_loop.py` and `test_scheduler.py` take `cancel`.

---

## OP-010 — The db-probe is blind when every usable connection slot is taken

**Status:** fixed 2026-10-09 — SC-04 at 100 % on vm-166: the probe stayed up, the alert fired, and the pulled alert's
incident `inc_03e42714762f` was DIAGNOSED (root cause the leaker;
[evidence](execution/history/OP-010/step-02/evidence.md); first run
[step-01](execution/history/OP-010/step-01/evidence.md)) · branch `task/OP-010-reserved-slot` · **Opened:**
2026-10-08 · **Found by:** `conantkd` (+ agent), risk review of the T-0020 PR · **Fix with:** its own small task
(vm-166 redeploy of `argus-lab-db` and SC-04 at 100 %)

**Problem.** The db-probe connects as `argus_monitor`, an ordinary role that competes for the same usable slots as
every client. `argus-lab-db` reserves only the superuser slots (`max_connections=20`,
`superuser_reserved_connections=3`, no `reserved_connections`). If a leak takes all 17 usable slots, the probe
cannot connect: it publishes only `argus_db_up 0`, `db_connection_usage` has no value, and the class does not match —
at the worst moment (unknown is never zero, by design). SC-04 opens 16 of 17 on purpose, so this case was not run.
Only the RB-003 branch (clients already failing) would catch it.

**Proposed fix (general).** Postgres 16: `reserved_connections=1` on the database and
`GRANT pg_use_reserved_connections TO argus_monitor`, so the monitoring role always has its own slot; the db-probe
already subtracts `reserved_connections` from the usable count. For real (non-lab) databases, the same two settings
become a documented prerequisite of the db-probe.

**Tests (red first).** The lab compose declares `reserved_connections` and the init script grants the role; SC-04
with `SESSIONS` equal to every usable slot still detects `postgresql_connection_exhaustion` (usage 1.0).

**Done when.** The settings are in the lab and documented, SC-04 at 100 % is DIAGNOSED on vm-166, and this item is set
to `fixed`.

**Done so far (2026-10-08).** Lab `reserved_connections=1` + the grant; the probe reports
`monitor_slot_reserved` / `argus_db_monitor_slot_reserved` and `inspect_database_health` warns without it (general:
a real database missing the prerequisite is visible); documented in `infrastructure/environment.md` and
`docs/INCIDENTS.md`. Tests `test_op010_reserved_slot.py` (red 6/6, green; suite 192 passed, 7 skipped). On vm-166:
SC-04 with 16 of 16 ordinary slots, the probe stayed up, usage 1.0 for 5 min, `DbConnectionsExhausted` firing.

---

## OP-011 — Two alerts on one target open two incidents (§6.4 correlation not implemented)

**Status:** open · **Opened:** 2026-10-09 · **Found by:** `conantkd` (T-0022 step 6)

**Problem.** In SC-03 the cache stopped and vm-166 fired two alerts on `argus-lab-api`: `DependencyProbeFailed` and
`ContainerUnhealthy` (its health check needs the cache). The scheduler pulled both in one pass and opened **two
incidents** (`inc_6f6f3aacfef8`, `inc_d02d9c397b7f`), both DIAGNOSED with the same class and root cause: twice the
reads and model cost, and two answers for one failure. Each alert is deduplicated by its identity (the next passes
say `duplicate`), but ARCHITECTURE §6.4 also says: an alert whose target and class match an open incident (within
`CORRELATION_WINDOW`, after the compatibility test) is **attached** to it, not opened as a new one. There is no
`application/correlation.py`; the webhook path has the same gap.

**Proposed solution (to discuss).** Implement §6.4 in the alert intake: (1) an open incident containing the
fingerprint → attach (exists as `duplicate`); (2) an open incident with the same target and class within the window,
compatible by a fresh detector run → attach as an `AlertOccurrence` (`attached`), `evidence_version` + 1; (3) else a
new incident. Alerts in the same pass are handled in order, so the second sees the first's open incident. The class is
known only after detection, so step 2 needs the detector at intake (the compatibility test already requires it).

**Done when.** A test with two alerts on one target and class gives one incident with two occurrences; SC-03 on
vm-166 gives one incident.
