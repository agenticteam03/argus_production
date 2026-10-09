# Parallel lanes — a proposal for three developers working at the same time

| Field | Value |
|---|---|
| Status | `proposed` (2026-10-09, `juanbetancurm` + agent) — needs the team's agreement in its pull request |
| Changes when accepted | `GIT_WORKFLOW.md`, `../agents/REVIEW_PROTOCOL.md`, `brain.py` (lease per VM, journal entries, roll-up), CI |
| Not an ACR | it changes how the team works, not `ARCHITECTURE.md` |

## Why

Three developers, but most work runs in a single line. Seen in the week of 2026-10-05:

1. **One lease covers both VMs.** Every deploy, scenario batch and evaluation run waits for the one holder, and that
   holder mostly waits for the run (a 5-run SC-01 batch ~45 min; 150 evaluation runs ~25 min).
2. **Every task PR edits the same Brain summaries** (`NEXT_STEP.md`, `journal/logbook.md`, `CURRENT_STATE.md`,
   `tdd/CURRENT_TEST_STATE.md`, `IMPLEMENTATION_PLAN.md`). Nearly every merge conflict this week was in these files.
3. **Stacked pull requests** (#45 ← #46 ← #47 ← #48): one change request on the bottom PR blocks the whole stack.
4. **The slow tests are not pytest.** The offline suite takes 2-5 min and CI runs it on every push. The slow parts are
   the VM runs, and nothing else can use the VMs while they run.

## The proposal

### 1. One lease per VM

- `brain.py start --vm vm-166` (or `--vm vm-095`, or both) claims only that VM. `session.json` holds one lease per VM;
  `/opt/argus-v18/SESSION` on each VM names its own holder (unchanged format).
- **Rule:** a change to the **agent on vm-095** (deploy, rebuild, `hosts.env`) needs **both** leases. vm-166's
  scenarios are investigated by vm-095's agent, so changing it under someone else's batch would invalidate that batch.
- A VM-local change on vm-166 (lab, target services, monitoring) needs only vm-166's lease. A run that changes
  nothing (the §21.2 evaluation's one-off container, a read-only check) needs only the lease of the VM it runs on.

### 2. Task PRs write only their own Brain files; one roll-up updates the summaries

- A task PR edits: its task file, its `execution/history/<task>/`, and **one journal entry file**
  `journal/entries/<YYYY-MM-DD>-<task>.md` (the same fields as today's logbook entries). Plus its code, tests and docs.
- It does **not** edit `NEXT_STEP.md`, `CURRENT_STATE.md`, `tdd/CURRENT_TEST_STATE.md`, `IMPLEMENTATION_PLAN.md` or
  `journal/logbook.md`. `brain.py lint` refuses those edits on a `task/*` branch (exception: the roll-up branch).
- **Roll-up:** after merges, `brain.py rollup` (a small PR, fast to review) appends the new entries to the logbook and
  regenerates the status lines of the summaries from the merged task files. Whoever merges last that day runs it.

### 3. Long runs are unattended jobs; tests run where they are cheap

- Scenario batches (`ops/e2e/run.py`) and evaluation trials (`ops/eval-run.sh`) run as background jobs on the VM and
  write a results file; the developer reads the verdict afterwards and works on something offline meanwhile.
- Locally: the tests near the change (`pytest tests/test_<area>.py`). CI runs everything on every push, split into
  parallel jobs: offline, Postgres, evaluation baseline (`python -m argus.evaluation --strategy baseline`), frontend.
  A PR merges only on a green CI, as today.

### 4. A lane board, file claims, no long stacks

- `NEXT_STEP.md` (edited only by the roll-up) starts with the **lane board**: per lane, the owner, the task, the
  files or modules it owns, and the VM lease it holds or needs next.
- **Hotspots** are claimed on the board before editing: `argus/infrastructure/wiring.py`, `argus/detectors/classes.py`,
  `config/inventory.yaml`, `config/signals.yaml`, `deploy/vm-095/compose.core.yml`, the migrations.
- PRs are based on `main`. A stack (a PR on another PR's branch) is allowed only with a same-day review promise from
  the reviewer, and at most two deep.
- **Reviews:** after the fast-track window (2026-10-12) every merge needs a second person, so each working day has one
  named reviewer (rotation). A PR waiting more than a day is the board's first item.

## The lanes, to start

| Lane | Owner | Work | VM lease |
|---|---|---|---|
| Integration | `conantkd` | merge #45-#48, both VMs on `main`, OP-009, SC runs on vm-166 | vm-166; both for agent deploys |
| Quality | `juanbetancurm` | T-0025 (class-registry decision, `disk_pressure` cases), runner catalogue (SC-04, SC-05), reviews | vm-095, for evaluation jobs |
| Frontend | `juanes6554` | T-0016 step 3 (read views on the API); reviews of docs and tests | none |

## Risks

- **A lease per VM is a new way to collide:** mitigated by the both-leases rule for the agent on vm-095.
- **The roll-up can lag:** the summaries are then a few hours behind; the task files stay the source of truth.
- **More parallel PRs need more reviews:** the daily reviewer rotation is the counterweight; without it the lanes
  queue up again.

## Order of work, if accepted

1. The lease per VM (`brain.py`, `GIT_WORKFLOW.md`), with tests.
2. Journal entries as files and `brain.py rollup`, with the lint rule.
3. CI split into parallel jobs; the runner and the evaluation as background jobs.
4. The lane board in `NEXT_STEP.md` and the reviewer rotation in `REVIEW_PROTOCOL.md`.
