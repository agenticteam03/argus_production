# T-0049 — Agent skills: the team's repeated procedures as reviewed, tested skills

| Field | Value |
|---|---|
| Status | `proposed` — plan only; S0 (governance) is the first pull request and needs `conantkd`'s review |
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
| S4 | **P2 skills.** `journal-and-task-status`: an entry in the roll-up format (`### Test state`, `### Next step` sections), a task status line with links, never a "done" without its PR. `ui-contract-samples`: regenerate only the samples whose shape changed. `vm-deploy`: **manual invocation only**; it prints the checklist (target, commit, SESSION, `nonint-check` before and after, migration before image). It never connects to a VM. | `.claude/skills/{journal-and-task-status,ui-contract-samples,vm-deploy}/` | yes | unrelated samples unchanged; no deploy command runs from the skill |
| S5 | **Evaluate the skills.** For each P0/P1 skill, 3–5 recorded tasks done with and without it. Record: reviewer corrections, failed blocks, trap fixtures caught, time. Activation checks (the skill is chosen when it should be and not otherwise) are done by hand. CI runs only the script tests, so no model calls in CI. | this task, a journal entry | no | the table below filled; a skill that doesn't help is removed |

**Hard fail for every step:** a skill or its script that approves, merges, pushes, deploys or touches a VM on its own.

## Runtime and operator track (after S2; each step its own ACR)

| Step | What | Depends on |
|---|---|---|
| R1 | **Evaluate before adding.** The class offers already planned (T-0036 to T-0040, T-0046 L6 `network.link_states`, T-0047 H5 step 2 `analysis.anomaly_summary`) are compared on the same cases: current class (control), and the class with the read offered for the model to choose. Diagnosis quality, calls, query cost and latency are recorded. | the evaluation batch, OP-014 step 8 |
| R2 | **Per-class pre-checks, only if they win.** A third arm: the same authorized reads run deterministically before the model, counted in the same `max_per_incident` budget, each a typed observation (`status`: success, missing, stale, error, denied). Proposed as an ACR only if it beats R1's second arm without any new permission. A class manifest **references** the detector, runbooks and signals and copies none of them. | R1, ACR-0022 (phase 22) |
| R3 | **Confirmed incident to proposed runbook diff.** From confirmed cases only, draft a diff to one runbook, with evidence and counterexamples, reviewed in a PR and checked by the evaluation. Never applied automatically. | T-0048 (confirmed feedback) |
| O1 | **Read-only on-call skill** for an operator's own agent: reads one incident through the authenticated API and drafts a handover note. GET only, a short-lived least-privilege token from the operator's credential store, never in the skill, the repo or the chat. | phase 16 deployed (ACR-0018: per-person sessions and permissions) |

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
| `code-bash-step` | | | | |
| `pr-review` | | | | |
| `acr-and-version-line` | | | | |
| `add-capability` | | | | |
| `db-migration` | | | | |
