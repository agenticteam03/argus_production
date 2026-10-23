# T-0049 — Agent skills: the team's repeated procedures as reviewed, tested skills

| Field | Value |
|---|---|
| Status | `in progress` — S0 (#268), S1 (#275), S2 (#277), S3 (#281, #285, #286), S4 (#283, #289, #290, #296) and S5's first evidence (#293) merged; R1: `container.detailed_logs` measured for `health_check_failed` and **not offered** ([evidence](../../execution/history/T-0049-R1/step-01/evidence.md)); the paired skill runs of S5 not measured yet |
| Phase | 24 (developer track, parallel to 15–23; the Argus runtime does not change) |
| Architecture | none for S0–S5 (development tooling only); the runtime steps R1–R3 and O1 each go through their own ACR |
| Branch | one branch per step: `task/T-0049-s<n>-<slug>` |
| Owner | `juanbetancurm` (+ agent); review `conantkd` |
| Needs the VM lease | no (S0–S5); R1 runs the evaluation on the VMs |

## Goal (plain language)

The same procedural mistakes keep coming back even though the rules are written down. Examples: a self-merge advised
from GitHub's `CLEAN` state while the branch was behind main (#245); PowerShell 5.1 stripping quotes inside native
command arguments; ARCHITECTURE version-line conflicts between parallel ACR pull requests. A **skill** packages one
such procedure for a coding agent: a short `SKILL.md`, the templates it fills, and small **tested scripts** that do
the exact checks. After this task, an agent that writes a `code.bash` block or reviews a pull request follows the
same steps every time, and a script catches the known traps before a developer runs anything.

## Principles (from the 2026-10-21 skills research guide, checked against this repository)

- **A skill says how, the code says what is allowed.** A skill never grants or widens anything. The write gate,
  `SELF_MERGE_PROTECTED`, `verify-main`, the class `tool_tags` and `max_per_incident` stay the only enforcement.
  "Never merge" written in a `SKILL.md` is guidance, not a control.
- **Reference the policies, don't copy them.** Each skill reads `brain/policies/CODE_BASH.md`,
  `brain/agents/REVIEW_PROTOCOL.md` and the other sources at run time; a copied rule drifts.
- **Exact checks are scripts with tests.** Parsing, quoting, ancestry and version ordering go in Python under the
  skill's `scripts/`, tested in `tests/skills/` by the normal CI. Judgement (is this merge resolution benign?) stays
  with the model and the reviewer.
- **Small and discriminative.** One skill per procedure, a description that says when to use it and when not.
  The main file stays short; details live in `references/` and load only when needed.
- **No runtime skill framework.** Argus already selects procedures per incident class: detectors, class
  `runbook_ids` and `branch_runbook_ids`, `tool_tags`, and the baseline strategy before the model loop. The runtime
  gets no `SKILL.md`. Any runtime change is an evaluated ACR (R1–R3).

## Steps

| Step | What | Paths | Protected | Done when |
|---|---|---|---|---|
| S0 | **Discovery and governance.** Check the guide's repository claims at the current `main` and record the inventory below. Add `.claude/skills/` to `SELF_MERGE_PROTECTED`: skills are agent instructions, like `brain/agents/`. One line in `AGENT_PROTOCOL.md`: skills live in `.claude/skills/`, and the policy a skill references wins over the skill. Record which agent hosts the team uses (Claude Code; `AGENTS.md` and `GEMINI.md` exist) and how each finds the folder. | `brain/tools/brain.py`, `tests/brain/`, `brain/agents/AGENT_PROTOCOL.md`, this task | yes | `conantkd` approves; `tests/brain` pins the new protected path |
| S1 | **`code-bash-step`** (P0). Writes one block in the `CODE_BASH.md` format from reviewed templates: approve on a reviewed head, merge if clean, post a comment, commit, push and open a pull request, a VM block with the SESSION check. `scripts/check_block.py` statically checks a block: the header (location tag, texts, `Expected`), the `Set-Location` and `git rev-parse` lines, `$ok` against the `VERDICT` denominator, no double quotes inside native-command arguments (PS 5.1 strips them), `${var}:` interpolation, `}` and `else` on one line, no heredoc for text, no `exit` in VM blocks, no address or secret, and only the current step's blocks. | `.claude/skills/code-bash-step/`, `tests/skills/test_check_block.py` | yes (after S0) | past real blocks pass; a fixture for each trap fails with a clear message |
| S2 | **`pr-review`** (P0). Follows `REVIEW_PROTOCOL.md` and produces findings, a recommendation and a review text **file**; it never runs `gh pr review`, `gh pr merge` or `git push`. Read-only helpers: `since_approval.py` (first-parent commits since the approved head, `git show --remerge-diff` per merge, a merge that only brings in main reported as such); `merge_ready.py` (the head contains the fetched `origin/main` by `git merge-base --is-ancestor`, never by `mergeStateStatus`; every review and comment read; checks green; protected paths through `brain.py`'s `is_protected`), which is the #245 lesson; `rollup_check.py` (every line of a removed journal entry is in the logbook or its summary file). | `.claude/skills/pr-review/`, `tests/skills/` | yes | fixtures: a clean PR, a branch one merge behind main (must say "not ready"), a merge resolution that hides a behaviour change (must ask for re-review) |
| S3 | **P1 skills.** `acr-and-version-line`: an ACR from `ACR-TEMPLATE.md`, and `version_line.py` that composes the ARCHITECTURE version line and changelog rows in canonical order and reconciles two branches without dropping a version. Editing the version line never approves the ACR. `add-capability`: the lifecycle seen in T-0036 to T-0040 and T-0047 H5 (`CapabilitySpec`, safety class and `ALLOWED_FIELDS`, `max_per_incident` in `config/policy.yaml`, wiring, the replay `FixtureExecutor`, tests); a new capability starts **offered to no class**, and the offer is a separate, evaluated change. `db-migration`: the SQL and SQLite pair, grants, both stores, the insert written first in the test (the #181 lesson), `argus db check`, `db-migrate.sh` before the new image. | `.claude/skills/{acr-and-version-line,add-capability,db-migration}/`, `tests/skills/` | yes | each script idempotent on its fixtures; a missing migration makes the test fail, not pass |
| S4 | **P2 skills.** `journal-and-task-status`: an entry in the roll-up format (`### Test state`, `### Next step` sections), a task status line with links, never a "done" without its PR. `ui-contract-samples`: regenerate only the samples whose shape changed; for `--keep-new`, restore shared IDs from their old JSON positions when referenced by another sample or a frontend test. `vm-deploy`: **manual invocation only**; it prints the checklist (target, commit, SESSION, `nonint-check` before and after, migration before image). It never connects to a VM. | `.claude/skills/{journal-and-task-status,ui-contract-samples,vm-deploy}/` | yes | unrelated samples unchanged; no deploy command runs from the skill |
| S5 | **Evaluate the skills.** For each P0/P1 skill, 3–5 recorded tasks done with and without it. Record: reviewer corrections, failed blocks, trap fixtures caught, time. Activation checks (the skill is chosen when it should be and not otherwise) are done by hand. CI runs only the script tests, so no model calls in CI. | this task, a journal entry | no | the table below filled; a skill that doesn't help is removed |

**Hard fail for every step:** a skill or its script that approves, merges, pushes, deploys or touches a VM on its own.

## Runtime and operator track (after S2; each step its own ACR)

| Step | What | Depends on |
|---|---|---|
| R1 | **Evaluate before adding.** The class offers already planned (T-0036 to T-0040, T-0046 L6 `network.link_states`, T-0047 H5 step 2 `analysis.anomaly_summary`) are compared on the same cases: current class (control), and the class with the read offered for the model to choose. Diagnosis quality, calls, query cost and latency are recorded. | the evaluation batch, OP-014 step 8 |
| R2 | **Per-class pre-checks, only if they win.** A third arm: the same authorized reads run deterministically before the model, counted in the same `max_per_incident` budget, each a typed observation (`status`: success, missing, stale, error, denied). Proposed as an ACR only if it beats R1's second arm without any new permission. A class manifest **references** the detector, runbooks and signals and copies none of them. | R1, ACR-0022 (phase 22) |
| R3 | **Confirmed incident to proposed runbook diff.** From confirmed cases only, draft a diff to one runbook, with evidence and counterexamples, reviewed in a PR and checked by the evaluation. Never applied automatically. | T-0048 (confirmed feedback) |
| O1 | **Read-only on-call skill** for an operator's own agent: reads one incident through the authenticated API and drafts a handover note. GET only, a short-lived least-privilege token from the operator's credential store, never in the skill, the repo or the chat. | phase 16 deployed (ACR-0018: per-person sessions and permissions) |

### R1 candidate preparation: `container.processes`

S2's offline ranking selected `container.processes` (`processes`) for `container_restart_loop` as the second candidate.
The six labelled `restart-*` cases now include Docker `/containers/<name>/top` snapshots shaped like the T-0037 gateway
response and its real-output evidence. These fixtures only make the read replayable; `container.processes` remains
unoffered to every class, and a class offer stays a separate measured R1 step. See the S4 R1b journal entry for the
case-level details and checks.

## Inventory at `main` `953331f` (2026-10-21; S0 re-checks it)

| Guide claim | At `main` |
|---|---|
| Eight incident classes in `argus/detectors/classes.py` with `runbook_ids` | yes: eight `IncidentClassSpec` entries |
| Runbooks `RB-001` to `RB-020` in `argus/runbooks/` | `RB-001` to `RB-021` (`RB-021` cascading overload is newer than the guide) |
| `branch_runbook_ids`, `knowledge.prior_incidents` | yes: catalog, classes, domain model, wiring, both runners |
| Migrations 007, 009, 010, 011 as patterns | yes, plus `012_incident_hypothesis.sql` (T-0047 H1) |
| Agent instructions | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` all point to `brain/agents/AGENT_PROTOCOL.md`; no `.claude/` folder yet |

## Evaluation (S5 fills it)

| Skill | Tasks with / without | Reviewer corrections | Traps caught | Kept? |
|---|---|---|---|---|
| `code-bash-step` | not measured yet / not measured yet | Several review-driven checker fixes; no task-level total | Checker caught the missing SESSION guard in EVS.1, `#${n}:` interpolation and lowercase labels; #275 also documents quoting and marker-boundary traps | Provisional keep; measure paired tasks |
| `pr-review` | not measured yet / not measured yet | One paired wording correction; one self-review logic fix | Fixtures cover behind-main `CLEAN` (#245), hidden merge behavior and lost roll-up text; live preview refused missing teammate approval on #268; #277 caught the 100-file self-merge limit | Provisional keep; measure paired tasks |
| `acr-and-version-line` | not measured yet / not measured yet | No correction recorded; paired pre-review was clear | Fixtures cover lost parallel versions, bad order, conflicts and missing rows/links; real ARCHITECTURE had 1.8.5/1.8.4 out of order and legacy rows (#281) | Provisional keep; measure paired tasks |
| `add-capability` | not measured yet / not measured yet | One test correction after #274 (#285 test, fixed on #274) | The #274 class offer was refused without `--allow-offer`; fixtures also catch the engine's silent default limit of 10, missing sensitive fields, wiring, replay and tests (#285) | Provisional keep; measure paired tasks |
| `db-migration` | not measured yet / not measured yet | One fixture correction and reapproval after #280 occupied migration 013 | Real #280 check flags missing positive `argus db check` inserts for both `013_webauthn.sql` tables; the same gap appeared in 006 (#286) | Provisional keep; measure paired tasks |

The counts above are deliberately not inferred from implementation tests, fixture runs, PRs, or review rounds. Those
records show concrete catches and the costs below, but no controlled task was run both with and without each skill.
"Reviewer corrections" records observed fixes, not an efficacy score. "Provisional keep" means the skill has at least
one useful observed catch; the paired runs below must still test whether it saves more rework than it adds.

### Observed costs and limits

- `code-bash-step` development recorded 12 false positives in a whole-file fixture and later guard/marker test
  failures, including 9 failing cases before the SESSION correction and 3 false accepts plus 2 refused marker cases
  before the final fix (#275 and its journal). These were checker-development failures, not developer-run block
  failures. The board does not count EVS.1 or other user-run blocks rejected before correction.
- `pr-review` needed the wording and self-merge corrections listed above. Its integrated-main full-suite run also
  exposed an unrelated main red fixed separately by #278; this added validation time, not a skill-caused failure.
- The `add-capability` checker test was pinned to main's state: it assumed `analysis.anomaly_summary` was unoffered.
  After #274 offered it to `container_restart_loop`, #274 CI went red; S1 fixed the test line on #274 (FIX.274), and
  the full suite passed 1727. The separate #285 CI cancellation was at Playwright installation and was rerun, not a
  skill defect. The `db-migration` fixed-013 fixture was a checker-test failure caused by #280's new migration; the
  checker correctly rejected the stale number and the fixture now chooses the next free number (#286).
- RED/GREEN test totals in the skill journals show checker-development cost and coverage. They are not task-level
  with/without observations; no task-level time or failed-block totals are recorded for these skills.

### P2 observations from recorded use

- `journal-and-task-status` (#283): its first review found 17 of 22 current task rows rejected by the original status
  grammar; accepting the repository's `#NNN` references and status formats fixed those false positives. Review then
  found `done` could bypass the PR-reference rule in trailing-word and markup-wrapped forms; the guard was tightened
  until every `done` form required a PR. This shows both value and reviewer correction cost; paired counts are not
  measured.
- `vm-deploy` (#289): the real `6c83da3..afb72e8` comparison initially omitted the `jwt_ed25519_key` file creation
  that DEPLOY-afb72e8 had needed by hand, and counted `deploy/target` and `deploy/monitoring` only for vm-166. Review
  caught both; the corrected output lists the secret-file step before any `up` and both VM targets. The helper was
  exercised on git diffs only; it did not connect to a VM.
- `ui-contract-samples` (#290) found three same-shape stale samples that the shape-only contract test missed:
  `events.json`, `incident.json`, and `incident-metrics.json`. Review also caught value-only changes being reverted
  and incomplete restoration after a failed regeneration; `--keep-new` and rollback were added. In the real refresh
  PR #291, Playwright then failed because regenerated IDs no longer matched IDs referenced by other samples. The
  original IDs were restored in the refreshed files; the skill needs a follow-up for shared generated IDs. The
  sample changes trace to detector PRs #38/#59/#60 (`events.json`), #44/#237 (`incident.json`), and #174/#188
  (`incident-metrics.json`, 63 current-window points rather than 61). PR #290 merged on 2026-10-22; #291 is still
  open. Paired counts are not measured.

### Proposed paired runs

For each P0/P1 skill, use the same three task inputs once with the skill and once without it, in fresh sessions with
the same policy and repository snapshot. Randomize which condition runs first; have the reviewer assess outputs
without seeing the condition. Record task success, reviewer corrections and severity, failed blocks, checker catches
and false positives, and elapsed time to review-ready. Keep activation checks manual: record whether the right skill
was selected when needed and avoided when irrelevant. RED/GREEN fixture counts are script validation, not paired
tasks. CI remains limited to script tests; do not add model calls to CI.

- `code-bash-step`: prepare a commit/push/PR block with exact staging; prepare a read-only or comment block with
  matching labels and verdicts; prepare a VM block with a SESSION guard and mutation-order checks without running it.
- `pr-review`: assess a current, green PR; refuse a branch behind main despite GitHub `CLEAN`; inspect a merge
  resolution that hides behavior change and verify removed journal text survives roll-up.
- `acr-and-version-line`: draft a valid ACR and version update; reconcile two parallel branches without dropping a
  version; refuse a same-version collision or missing changelog row/link while preserving legacy rows.
- `add-capability`: add a safe read with a positive call limit; add a sensitive read with its allowed fields and
  replay executor; keep a new read unoffered, then check the separate class offer with and without `--allow-offer`.
- `db-migration`: add the next numbered table with both stores and grants; put a succeeding db-check insert before
  refusal cases; add an insert-only table and verify update/delete refusals and SQLite triggers.
