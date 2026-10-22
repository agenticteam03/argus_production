# Open problems and pending team decisions

When a problem is fixed, set its status to `fixed` with the date, and add a journal entry if it is significant.
**Status:** `open` · `in progress` · `fixed` · `dropped` (with reason) · decisions: `pending` · `decided`

| ID | Item | Status | Opened |
|---|---|---|---|
| **D-001** | Cross-host path and alert direction: architecture text vs the running system | **decided** 2026-10-08 (`conantkd`): option B as transport profiles, [ACR-0003](architecture/changes/ACR-0003-transport-profiles.md); second approval in the T-0022 PR | 2026-10-02 |
| **D-002** | Move the runbook library into this repository (the architecture expects it there) | **decided and done** 2026-10-02 | 2026-10-02 |
| **D-003** | The class registry: keep the model or switch a class to the deterministic baseline (§21.2 rule) | **decided** 2026-10-13 (`juanbetancurm`): `dependency_unavailable` and `nginx_upstream_failure` to `baseline`, the other six keep their strategy; revisited in OP-013 | 2026-10-09 |
| OP-001 | Runbook `detector` metadata uses old or empty class names | fixed 2026-10-09 (PR #44 merged) | 2026-09-30 |
| OP-002 | P0 safety gaps of the runbook library not yet reconciled with architecture v1.8 | open | 2026-09-30 |
| OP-003 | Runbook safety classes not mapped to `CapabilitySpec.risk` | in progress (ACR-0026) | 2026-09-30 |
| OP-004 | LangGraph checkpoints grow forever; checkpoints of failed runs are orphaned | in progress — offline tests pass; VM dry run and approved apply pending | 2026-10-05 |
| **OP-005** | The `restarts_10m` signal undercounts restarts of a container younger than its window | **fixed** 2026-10-09 — verified on both VMs (PR #41) | 2026-10-05 |
| OP-006 | LangGraph `recursion_limit` is fixed at 100 and can be too small for larger step budgets | fixed 2026-10-05 | 2026-10-05 |
| **OP-007** | A dependency probe disappears while its owner is restarting, hiding the cause of a crash loop | fixed 2026-10-07 (`owner_active`: running or restarting; deployed on vm-166) | 2026-10-07 |
| **OP-008** | Postgres backups are never rotated, and the backup's consistency check will stop once the scheduler writes often | in progress — offline implementation and Docker tests pass; VM dry run and approved apply pending | 2026-10-07 |
| OP-009 | A worker that loses its lease keeps running the incident; with two workers the same run could execute twice | fixed 2026-10-08 (`task/OP-009-lease-loss`: the renewer retries, a lost claim cancels the run) | 2026-10-08 |
| OP-010 | The db-probe cannot connect when every usable slot is taken, so `postgresql_connection_exhaustion` cannot fire at 100 % | **fixed** 2026-10-09 — SC-04 at 100 % DIAGNOSED from the pulled alert | 2026-10-08 |
| **OP-011** | Two alerts on one target open two incidents: §6.4 correlation is not implemented | **fixed** 2026-10-09 — SC-03 on vm-166 gives one incident (ACR-0004) | 2026-10-09 |
| OP-013 | D-003 was decided on the same cases the baseline's rules were written from: its 1.00 is an upper bound | open | 2026-10-13 |
| **OP-014** | The self-merge rule relies on the tests: gaps where a green CI does not yet mean "safe to merge" | in progress — steps 1-7 and 10 done (TEST-HARDEN-1, the CI gates, Vitest coverage 2026-10-21); 8, 9, 11-13 left | 2026-10-17 |
| **OP-015** | ARCHITECTURE §14 says the approval/action machinery "exists from the start"; the code has none of it | open — implemented by ACR-0019 (phase 18) if accepted; until then the text must say "designed, not built" | 2026-10-18 |
| **OP-016** | `policies/SECURITY.md` lists "the team's shared Argus password"; §17.3 and ACR-0011 require one account per person | open — fixed in phase 15 | 2026-10-18 |
| **OP-017** | The frontend's dependencies have known advisories: React Router (production, moderate), Vite, Vitest and esbuild (dev tooling, up to critical); every fix is a major upgrade | **fixed** 2026-10-21 — React Router 7, Vite 8, Vitest 5; CI runs `npm audit --audit-level=high` on every dependency | 2026-10-20 |

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

**Status:** fixed 2026-10-09 (`task/OP-001-runbook-detectors`, PR #44 merged) · **Opened:** 2026-09-30

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

**Status:** open · **Opened:** 2026-09-30 · **Reviewed:** 2026-10-20 by `conantkd` (+ agent), every gap checked
against ARCHITECTURE 1.8.20, the code on `main` and the NEXT-PHASE ACRs (`task/OP-002-gap-review`)

**Problem.** The library's `ARGUS-CAPABILITY-GAPS.md` lists eight **P0** gaps written against an older code base.
Each must be settled in the architecture (ACR) before the related implementation.

**Review (2026-10-20).** Four kinds of answer: covered by the text; built but missing from the text (the code says
"lab addition"); assigned to a proposed ACR; still open.

| Gap | Asks for | Finding (evidence) | Resolution |
|---|---|---|---|
| G-001 Deployment profiles | named profiles; a missing profile fails closed | **built, not in the text:** `config/policy.yaml` declares `profile`, and `argus/policy/engine.py` refuses to start without `lab` or `production`; the profile selects `allowed_safety_classes`. §13.1 names neither. `config/policy.yaml` says `production` although the deployment is the lab, and ACR-0018 makes separation of duties depend on the profile | **closed** by ACR-0027 (#216): §13.1 states the profile; which profile the lab runs is decided in phase 16's ACR-0018 pull request |
| G-002 Typed prerequisites | preconditions as typed predicates on fresh, identity-bound evidence | §13.1 still shows free text (`preconditions: ["restart_count >= 3"]`); ACR-0019 §3.4 replaces it: action-card `preconditions` over fresh observations, a minimal interpreter (comparisons, `in`, `and`, `or`, never `eval`), re-evaluated at precheck | **ACR-0019** (proposed), phase 17 |
| G-003 Observation provenance | source vs collection time, coverage, units, partial state, identities | **built, not in the text:** `CapabilityResult` / `Observation` / `EvidenceRecord` carry `source_time`, `units`, `partial`, `coverage`, `identities` (`argus/domain/model.py`, stored by `invoke_capability.py`); per-series freshness in `config_adapters.py`. §5.4 and §12.3 list none of them | **closed** by ACR-0027 (#216): the fields in §5.4, §10 and §12.3 as built |
| G-004 Approval binding | an immutable proposal bound to what it acts on, previews | §14 binds the proposal by digest; ACR-0019 §3.6 freezes it and adds the precheck preview (`dry_run`) to the digest and the approval view | **ACR-0019** (proposed), phase 18 |
| G-005 Verification windows | stability windows, provisional vs final recovery | §15.1 calls one fresh healthy sample `recovered_verified`; nothing waits for stability. ACR-0019 gives each action card a `verify` with signals and a window, but not two states | **ACR-0019**, with one addition asked in its review: recovery is provisional until the card's window holds, then final; only final counts as `recovered_verified` |
| G-006 Data minimization | per-source field allowlists, literal redaction | redaction is built and stated (§5.4, `capabilities/redaction.py`, `container.inspect` env/mounts); no field allowlist exists. ACR-0026 decides which reads need one (`READ_ONLY_SENSITIVE`) | **ACR-0028** accepted (#218) and applied in `task/ACR-0028-apply-field-allowlists` (1.8.25): `allowed_fields` per sensitive capability, enforced in the dispatcher before redaction; closed when it merges |
| G-007 Helper semantics | missing or partial data never becomes healthy or the root cause | **built, partly in the text:** missing values are `None`, never 0 (`MetricSnapshot`); a blind host is a finding, not healthy (`detectors/classes.py`); stale metrics end `undiagnosable` (§1.3, §9); the topology says `unknown`, never ok (§7.1). Tests: `test_t0027_blind_spot`, `test_t0032_prometheus_down`, `test_sc04_pg_connections`, `test_e2e2_evidence_gaps`. The rule itself is not stated once | **closed** by ACR-0027 (#216): the rule in §12.3, `None` in §5.4's `MetricSnapshot` |
| G-008 Corpus/dispatcher separation | runbook ids from metadata, bounded passages, tools never from runbook text | **covered:** §15.3; a `MISSING TOOL REQUIREMENT` name is never offered (§15.3); tools come only from the catalog by class tags (`runner.py`, `graph_runner.py`); no write is registered, and the standing write-gate test (`tests/test_write_gate_standing.py`) checks that a model-proposed restart is never executed | **closed** |

**Next.** ACR-0027 (#216, merged) wrote down G-001, G-003 and G-007; the G-005 addition in ACR-0019's review;
G-006 applied by ACR-0028 (`task/ACR-0028-apply-field-allowlists`).

**Done when.** Each gap is covered, changed through an ACR, or dropped with a reason. Today: G-008 closed; G-002 and
G-004 wait for ACR-0019 to be applied; G-001, G-003 and G-007 closed by ACR-0027 (#216); G-005 open as above;
G-006 applied by ACR-0028 (`task/ACR-0028-apply-field-allowlists`).

---

## D-003 — The class registry: model or baseline per class

**Status:** decided 2026-10-13 by `juanbetancurm` (revisited in OP-013) · **Opened:** 2026-10-09 (T-0025), measured again in EVAL-2 (2026-10-12)

**The question.** §21.2's rule: a class keeps the model only if it matches or beats the deterministic baseline on
the evaluation cases. Switching a class to `baseline` is a data change in the class registry, so it is the team's.
EVAL-2's table ([`tasks/completed/EVAL-2-model-trials.md`](tasks/completed/EVAL-2-model-trials.md), 5 trials, 55
cases): the model matches or beats the baseline for `cpu_saturation`, `monitoring_blind_spot`,
`postgresql_connection_exhaustion` and `disk_pressure`; `nginx_upstream_failure`, `dependency_unavailable`,
`container_restart_loop` and `health_check_failed` sit 0.04-0.20 under it, mostly by a safe escalation or a word.
Hard counts are 0 in every run. The baseline's rules were written with these cases, so the comparison favours it.

**Since then.** EVAL-3 (#93, #99) relabelled `restart-sigkill-01` (RB-008: escalate); EVAL-4 (#100) re-grades the
health wording offline. In review: EVAL-6 (#129, health 0.88 → 0.96) and the evaluation of `main` `d34f0cb` (#118).

**Done when.** Each of the four classes under the baseline is decided (keep the model, or `baseline`), recorded in
the journal, and any registry change made in its own pull request.

**Decision (2026-10-13).** Follow §21.2 as written, counting **all** of a class's evaluation cases (ambiguous ones
included), 5 trials: the baseline re-run offline on `main` `f51c2b4`, the model from EVAL-main (`d34f0cb`) re-graded
by EVAL-6.

| Class | Model | Baseline | Strategy |
|---|---|---|---|
| `dependency_unavailable` | 27/30 = 0.90 | 30/30 = 1.00 | **`baseline`** (was `model_loop`) |
| `nginx_upstream_failure` | 23/25 = 0.92 | 25/25 = 1.00 | **`baseline`** (was `plan_then_reason`) |
| `health_check_failed` | 29/30 = 0.97 | 25/30 = 0.83 | `model_loop`, kept: the baseline diagnoses `ambiguous-health-no-cause`, where the right answer is to escalate |
| `container_restart_loop` | 0.97 | 0.83 | `model_loop`, kept |
| `disk_pressure` | 0.97 | 0.88 | `confirm_then_reason`, kept |
| `cpu_saturation`, `postgresql_connection_exhaustion` | 1.00 | 1.00 | `model_loop`, kept (matches) |
| `monitoring_blind_spot` | 1.00 | 1.00 | `evidence_pack`, kept |

The evaluation CLI's per-class table counts only the `class` cases; the ambiguous ones count toward abstention.
Counted that way, health looked like 0.96 vs 1.00; with its ambiguous case it is the other way round. The new
capabilities (T-0036 to T-0040, the snapshot) stay offered to no class: offering one needs an evaluation batch first.
Registry change: `argus/detectors/classes.py`; test `tests/test_d003_class_registry.py`.

---

## OP-013 — D-003 rests on cases the baseline was written from

**Status:** open · **Opened:** 2026-10-13 (D-003)

**Problem.** The baseline's rules were written while looking at the 55 evaluation cases, so its 1.00 on
`dependency_unavailable` and `nginx_upstream_failure` is an upper bound, not its performance on new incidents. The
model's misses on those classes are mostly safe escalations (hard counts 0 in every run), and one nginx miss is a
disputed label (`nginx-slow-check`: nginx's 2 s timeout vs the upstream's 5 s, EVAL-6).

**Fix.** A held-out set: at least 5 new cases per class, written without changing the baseline's rules, then both
strategies, 5 trials each. Re-decide each class by §21.2 on those results, or propose an ACR if the rule itself should
change (for example "within 0.10 of the baseline and hard 0").

**Done when.** The held-out results are recorded and each class's strategy is re-decided in its own pull request.

---

## OP-014 — The self-merge rule relies on the tests

**Status:** in progress: steps 1-3 done (`TEST-HARDEN-1`, 99badb3: the Docker tests run in CI, the prompt-injection
cases in `tests/test_op014_prompt_injection.py`, the timing test checks mechanics only), steps 4-7 and 10 done
(below); left: 8 (the scheduled model evaluation), 9, 11-13 · **Opened:** 2026-10-17 (the self-merge rule,
`agents/REVIEW_PROTOCOL.md`) · **Owner:** the team

**Problem.** Under the self-merge rule, a green `test` + `frontend` on the last push replaces a teammate's review for
everything outside the protected paths. CI is already broad: Brain audit and lint, gitleaks over the full history,
about 130 pytest files with a throwaway Postgres, the offline baseline evaluation and its safety cases (a planted
secret never reaches the model, no cross-host read, no action), the write-gate standing test, the PromQL cases, and
the frontend's ESLint, Vitest, build and Playwright. But a green CI does not yet cover:

| # | Gap | Why it matters for self-merge |
|---|---|---|
| 1 | **Docker-gated tests are skipped in CI**: `ARGUS_TEST_DOCKER` is never set, so the credential-isolation check (`tests/test_tool_isolation.py`) and the real-Docker backup tests (`tests/test_db_backup.py`) never run there; the real-Nginx edge tests (`tests/test_acr0011_ui_edge.py`) run only if the runner has Docker | a change that breaks secret isolation or the public edge passes CI |
| 2 | **No prompt-injection tests**, although §22.3 item 10 requires injection fixtures | a change to context assembly or redaction can let target text steer the model |
| 3 | **A flaky timing test**: `tests/test_mcp_child.py::test_benchmark_compares_direct_and_mcp_on_the_same_read` (p95 < 100 ms) fails under load | a red-by-chance run blocks merges; people learn to ignore red |
| 4 | **No check that new code is tested**: "red seen" is a written record only; there is no coverage measurement | an untested change merges green |
| 5 | **The model's diagnosis quality is not in CI**: only the deterministic baseline runs offline; prompts, strategies and the class registry can lower the 0.97 unnoticed | a quality regression merges green |
| 6 | **No static analysis or dependency audit** for Python, the frontend, the Dockerfiles, the shell scripts or the workflows | a vulnerable dependency or an obvious bug pattern merges green |
| 7 | **The protected-path list is a deny list** (SLSA's threat model warns that path exemptions can be abused, e.g. code hidden in a "documentation" path) | a new enforcement-relevant file is self-mergeable until it is added to `SELF_MERGE_PROTECTED` |

**Fix, in order.** (Online research, 2026-10-17: OpenSSF Scorecard checks, SLSA source-track discussion, mutation and
diff-coverage gates, LLM injection regression testing, CI security scanners.)

*Done — `task/TEST-HARDEN-1` (99badb3):*
1. Run the Docker tests in CI (`ARGUS_TEST_DOCKER=1` on the Linux runner, which has Docker) and make them required.
2. Prompt-injection regression cases: instructions planted in container logs, a file read, an HTTP body and a peer
   finding; assert they are wrapped as data, never change the class or the root cause, never add a tool call outside
   the allowlist, and never reach the model unredacted. Fail the build on these objective signals.
3. Make the timing test robust (compare medians with a margin, or move the p95 budget to an opt-in benchmark run).

*Next — one PR each, each new job added to `SELF_MERGE_CHECKS` in the same PR:*
4. **Coverage on changed lines:** `pytest-cov` + `diff-cover` (or `pytest-nlcov`) failing under 80 % of the PR's
   changed lines; Vitest coverage thresholds for `frontend/`. A changed-lines gate never blocks on old, untested code.
   *Done 2026-10-20 for Python (`task/OP-014-4-7-ci-gates`):* the `test` job runs the suite under `pytest-cov`
   (`argus/`, `services/`) and `diff-cover` fails a PR whose changed lines there are under 80 % covered (against
   `origin/main`). Run in CI only: the full suite under coverage ran out of memory on a laptop. *Done 2026-10-21
   for `frontend/` (`task/OP-014-4-vitest-coverage`, after OP-017's Vitest 5):* `npm test` runs Vitest with
   `@vitest/coverage-v8` over every source file and fails under floors set just below the current figures; raised
   as tests are added, never lowered. First 33 / 33 / 28 / 26 % (lines, statements, functions, branches); then
   43 / 43 / 39 / 40 % with tests for SafeMarkdown, the incident's answer, why-card, timeline, evidence, audit and
   charts (`task/OP-014-frontend-tests`); then 45 / 44 / 41 / 44 % with the shared badges, live pill, tabs, runbook
   card and incident row (`task/OP-014-frontend-tests-2`). A floor, not a
   changed-lines gate: the pages are mostly covered by Playwright, which it does not count.
5. **Static analysis (SAST):** `ruff` for Python; `bandit` or `semgrep` (OWASP / Python rulesets) failing on high
   severity. CodeQL code scanning is not available for private repositories on the free plan, so these run as
   plain CI steps without SARIF upload. *Done 2026-10-20 (`task/OP-014-5-static-analysis`):* `ruff` (default rules, E731 ignored)
   and `bandit` at high severity on `argus/`, `services/` and `ops/`, both clean; bandit's 20 medium findings were
   reviewed (SQL built from constant table names and placeholders, the API's bind address, allowlisted URL reads) and
   are not a gate yet.
6. **Dependency audit:** `pip-audit` and `npm audit --audit-level=high` (or OSV-Scanner) on every PR; Dependabot
   alerts on. *Done 2026-10-20 for Python and the UI's production dependencies* (steps in the
   `test` and `frontend` jobs, so `SELF_MERGE_CHECKS` is unchanged); the dev tooling's advisories are OP-017.
7. **Workflow, image and script linting:** `zizmor` for `.github/workflows/`, `hadolint` for the Dockerfiles,
   `shellcheck` for `ops/*.sh`, Trivy config/filesystem scan. **Pin every action by commit SHA**: the Trivy action
   itself was compromised in March 2026, and pinned dependencies are an OpenSSF Scorecard check. *Pinning done 2026-10-20
   (`task/OP-014-7-pin-actions`):* the four actions by commit SHA, and the gitleaks download checked against its
   published SHA-256. *Linting done 2026-10-20 (`task/OP-014-4-7-ci-gates`):* `zizmor` on the workflows (3 medium
   findings fixed: `actions/checkout` no longer persists the git token, `persist-credentials: false`), `hadolint` on
   the four Dockerfiles (binary checked against its SHA-256; DL3008/DL3018, unpinned distro packages, ignored in
   `.hadolint.yaml` with the reason), `shellcheck -S warning` on `ops/*.sh` (one real finding fixed in
   `db-backup.sh`: `>&"$fd" 2>/dev/null` read as both streams, now `1>&"$fd"`; three `hosts.env` sources and
   `ui-cert.sh`'s own `dirs` function annotated), and Trivy 0.75.0's configuration scan at high and critical (the
   binary, checked against its SHA-256, never the action). Steps of the `test` job, so `SELF_MERGE_CHECKS` is
   unchanged. **Left:** Trivy's one finding, DS-0002 (root in the container) on `services/target/Dockerfile` and
   `deploy/vm-095/tunnel/Dockerfile`, is an exception for those two files only (`.trivyignore.yaml`): the target
   services read the host's Docker socket and allowlisted host files, and the tunnel reads its key mounted from the
   host, so a non-root user needs a VM change (the docker group, key ownership) and a deploy with its lease.
8. **Model quality:** run the model evaluation (§21.2) on a schedule (weekly) and record the result; until then a
   change under `argus/orchestration/`, `config/signals.yaml`, the class registry or the runbooks asks for a
   teammate's review (REVIEW_PROTOCOL.md, "The tests this rule relies on").

*Later:*
9. **Mutation testing** (`mutmut`) on the safety-critical modules (`argus/policy/`, `application/invoke_capability.py`,
   redaction), weekly, with a threshold that starts at today's score and only goes up. *First run 2026-10-22, local
   (`task/OP-014-9-mutation`):* `argus/policy/` and `invoke_capability.py`, mutmut 3.3.1 in a container; 889 mutants:
   525 killed, 59 survived, 305 timed out (a loaded laptop: re-run them before counting). `argus/policy/` had one
   survivor; the others were in the combined-capability path. `tests/test_op014_mutation_invoke.py` kills 51 of the
   59; the 8 left are equivalent (a `getattr` default never used, `model_dump` mode on string-only fields, a context
   used only when the target is missing). *Redaction 2026-10-22 (`task/OP-014-9-mutation-redaction`):* 204
   mutants, 136 killed, 58 survived, 10 timed out; `tests/test_op014_mutation_redaction.py` kills 42 of the 58, the
   16 left are equivalent (sort order of spans that are sorted again, `find` from `start + 2`, merging spans that
   only touch). *Re-run with 3 workers (`task/OP-014-9-mutation-read-path`):* the policy and the read path, 889
   mutants: 649 killed, 66 survived, 174 timed out. 58 survivors were new (hidden among the first timeouts): the audit
   trail and the stored evidence of an ordinary read. `tests/test_op014_mutation_read_path.py` kills 56; the 2 left
   and the 8 of the first run are equivalent. *The 174 timeouts re-run with 2 workers
   (`task/OP-014-9-mutation-decisions`):* 93 killed, 45 survived, 36 still timed out;
   `tests/test_op014_mutation_policy_decisions.py` kills 37, the 8 left are equivalent. **Left:** 36 timeouts, and
   the weekly CI job (`.github/`, a teammate's review).
10. **Property-based tests** (Hypothesis) for redaction, target parsing and the policy engine. *Redaction and target
    parsing done 2026-10-20 (`tests/test_op014_property_based.py`).* They found a real gap: a token glued to a
    non-ASCII letter (`é<token>`) escaped the high-entropy rule, because Unicode `\b` saw no word boundary; fixed with
    `re.ASCII` there and on the `Bearer` and `sk-` rules. *The policy engine done 2026-10-20 too*
    (`tests/test_op014_property_policy.py`, tests only: `PolicyEngine.check` fails closed, the inspection policy never
    allows a path that is not normal or that the deny floor names, even under an allowlist of `/`). No gap found;
    three injected bugs (no scope check, no deny list, no path normalization) were caught.
11. **LLM red-team scan** on a schedule (promptfoo for the application, garak for the model) next to the fixed
    regression cases of step 2.
12. **Accessibility checks** in Playwright (axe-core) on the main pages. *Done 2026-10-21 (`task/OP-014-12-a11y`):*
    `frontend/e2e/a11y.e2e.js` runs axe-core (WCAG 2 A and AA) on login, dashboard, incidents, an incident and
    runbooks; any violation fails the `frontend` job. *Contrast fixed 2026-10-22 (`task/OP-014-12-contrast`):* the
    "updated" clock uses `text-muted` (6.3:1, was `text-muted/60` 2.93:1); solid buttons with white text use
    `bg-accent-solid` `#2563eb` (5.2:1; hover `#1d4ed8` 6.7:1, was `bg-accent` 3.67:1); `color-contrast` is no
    longer excluded. Step 12 is done.
13. **OpenSSF Scorecard** run monthly as a health signal for the repository's practices.

**Done when.** Steps 1-8 are merged and required; the self-merge rule's protected-path list is reviewed again with
them (gap 7). Steps 9-13 are tracked as tasks.

---

## OP-015 — §14's approval and action machinery is described as built, but is not

**Status:** fixed 2026-10-20 (`task/PHASE-15-foundations`: the text no longer claims it; ARCHITECTURE 1.8.21) · **Opened:** 2026-10-18 (the NEXT-PHASE proposal) · **Found by:** `juanbetancurm` (+ agent)

**Problem.** ARCHITECTURE §14 says: "In this release no write capability is released, but the machinery, its tables
and its tests exist from the start so that the first release changes no core code." `IMPLEMENTATION_PLAN.md` phase 9
lists "HITL against a **fake** action endpoint" and the phase is at 90 %. The code has none of it:
- no `action_proposal`, `approval`, `notification_outbox`, `resume_intent`, `action` or `target_hold` table in
  `deploy/migrations/`;
- no `capabilities/write_contract.py`;
- no approval or hold route in `argus/adapters/inbound/http.py`;
- no fake action gateway;
- the UI's `decideApproval` answers 403 by design.

What exists is the closed write gate and its standing test (T-0031).

**Fix.** If ACR-0019 is accepted, phase 18 builds the machinery against a fake gateway. Until then, the next
ARCHITECTURE change touching §14 states "designed, not built", and phase 9's line in the plan drops the HITL item.

**Done when.** The §14.4 failure-injection and §22.2 binding suites run in CI, or the text no longer claims they
exist. *Done 2026-10-20 the second way:* §14 says "designed, not built" (1.8.21), and the plan's phase 9 and its
"Escalation / approval" exit line no longer list HITL against a fake endpoint (it is phase 18).

---

## OP-016 — `SECURITY.md` lists a shared team password

**Status:** fixed 2026-10-20 (`task/PHASE-15-foundations`: the row is replaced; no shared account on vm-095) · **Opened:** 2026-10-18 · **Found by:** `juanbetancurm` (+ agent)

**Problem.** `policies/SECURITY.md`'s secrets table has a row "The team's shared Argus password | each developer's
password manager". ARCHITECTURE §17.3 (ACR-0011) says "Every login reachable from the Internet is one account per
person (no shared password)", and the review of ACR-0011 required it. A shared credential also makes an approval or
a terminal session impossible to attribute (ACR-0018, ACR-0019, ACR-0020).

**Fix.** In phase 15: confirm on vm-095 that every login is personal (a read-only query of the `principal` table's
ids and kinds; `argus user` has only `add` and `disable`), disable any shared account (`argus user disable`), and replace the row with "Each developer's Argus password | their password manager; an Argon2 hash in
Postgres".

**Done when.** The row is replaced and no shared account exists. *Row replaced 2026-10-20* ("Each developer's Argus
password (one account per person, no shared login)"); the read-only `principal` query on vm-095 (run by `conantkd`, ids, kinds, roles and
`disabled` only) lists five principals, all `human` and each one person's: `conantkd`, `juanbetancurm`,
`juanes6554` (operators, enabled), `conantkd-viewer` (the temporary viewer of the D.4 check) and `olav`, both
disabled. No shared account, so nothing to disable.

---

## OP-017 — The frontend's dependencies have known advisories

**Status:** **fixed** 2026-10-21: `react-router-dom` 7.18.4, `vite` 8.3.5 and `vitest` 5.0.5 (#229, #242); CI's
`frontend` job runs `npm audit --audit-level=high` on every dependency (#244) · **Opened:** 2026-10-20 (OP-014 step 6, `npm audit`) · **Found by:** `conantkd`
(+ agent) · **Owner:** the frontend lane (T-0016)

**Problem.** `npm audit` in `frontend/` on 2026-10-20 reports the following. Python: `pip-audit` found nothing.

| Package | Severity | Shipped in the UI image? | Advisory | Fix |
|---|---|---|---|---|
| `react-router`, `react-router-dom` 6.x | moderate | **yes** | open redirect via a backslash in `<Link>` / `useNavigate` (GHSA-wrjc-x8rr-h8h6); a constructor injection in SSR hydration (GHSA-337j-9hxr-rhxg; the UI has no SSR) | `react-router-dom` 7.18.4 (major) |
| `vite` 5.x, `esbuild` ≤ 0.24.2 | high, moderate | no (build and dev server only) | path traversal in optimized deps `.map` handling; any site can query the dev server | `vite` 8.3.4 (major) |
| `vitest` 3.x, `@vitest/mocker`, `tinypool` | critical | no (tests only) | prototype pollution to code execution in worker options; file read via a redirect mock | `vitest` 5.0.5 (major) |

**Why it matters.** The built UI is static files served by nginx: only React Router ships. The UI does not navigate to
user-supplied URLs, so its open redirect is not reachable today. The tooling advisories matter on a developer's
laptop (`npm run dev`, the dev server) and in CI.

**Fix.**
1. Done (OP-014 step 6): CI's `frontend` job runs `npm audit --omit=dev --audit-level=high`, and `test` runs
   `pip-audit`. A new high advisory in what ships fails the build.
2. In the frontend lane: upgrade `react-router-dom` to 7, then `vite` and `vitest` together. Each is a major upgrade,
   with the Vitest and Playwright suites as the check.
   - Done 2026-10-21: `react-router-dom` 7.18.4 (released 2026-09-15). No code change: the UI uses only the classic
     API (`BrowserRouter`, `Routes`, `Link`, `NavLink`, the hooks), unchanged in 7. Lint, Vitest (131), the build and
     Playwright (21, with the read-only guard) pass; `npm audit --omit=dev` finds nothing.
   - Done 2026-10-21: `vite` 8.3.5 (Rolldown inside), `@vitejs/plugin-react` 6.1.2 and `vitest` 5.0.5 together. No
     code or config change: `vite.config.js` uses only `defineConfig`, `searchForWorkspaceRoot` and the server and
     preview hooks. Lint, Vitest (136), the build and Playwright (21) pass; `npm audit` finds nothing, dev included.
3. Then raise the npm gate to every dependency (`npm audit --audit-level=high`, dev included).

**Done when.** `npm audit --audit-level=high` passes on the whole tree and CI runs it.

---

## OP-003 — Runbook safety classes not mapped to `CapabilitySpec.risk`

**Status:** in progress 2026-10-20 ([ACR-0026](architecture/changes/ACR-0026-safety-classes.md),
`task/ACR-0026-safety-classes`): §12.3 has one scheme of five classes, `risk` is gone, `FORBIDDEN` is never
registered, and the four reads that were wrongly `READ_ONLY_SAFE` (two log reads, the snapshot, directory sizes) are sensitive. **Left:** the runbooks' "Safety class"
column (54 rows in 19 runbooks differ from the catalog) is rewritten from it with a test, and G-006 gives the
sensitive reads their field allowlists · **Opened:** 2026-09-30

**Problem.** The library's conventions classify operations as `READ_ONLY_SAFE`, `READ_ONLY_SENSITIVE`,
`MUTATING_LOW_RISK`, `MUTATING_HIGH_RISK`, `FORBIDDEN`; architecture §12.3 uses `risk: low | medium | high | very_high`
plus `permission: read | write_hitl`. They do not map cleanly (sensitive reads need allowlists; `FORBIDDEN` has no
equivalent).

**Fix (to discuss, ACR).** Adopt the five classes as `safety_class`, derive `permission` from it; sensitive reads get
mandatory field allowlists (ties to G-006); `FORBIDDEN` operations are never registered; classify every capability in §12.2.

**Done when.** §12.3 has one scheme; every capability has a class; policy and redaction rules refer to it.

---

## OP-004 — Checkpoint retention (in progress)

**Status:** in progress: built (#42) and its first approved `--apply` ran on vm-095 on 2026-10-14 (nothing old
enough); a dry run on 2026-10-21 (DEPLOY-NIGHT) still finds nothing past 30 days (`threads=0 checkpoints=0`). **Left:**
the daily timer, a team decision (it runs without a lease; see the task). Was: in progress 2026-10-09
(`task/OP-004-checkpoint-cleanup`, offline tests passed; VM dry run and approved apply pending); proposal accepted
2026-10-05 (PR #7) · **Opened:** 2026-10-05 · **Found by:** `conantkd` (T-0013 review)

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

**Status:** in progress: built (#51) and its first approved `prune --apply` ran on vm-095; a preview on 2026-10-21
(DEPLOY-NIGHT) would remove 13 backup sets (2026-10-13 and 14), nothing removed. **Left:** a scheduled prune, a team
decision. Was: in progress 2026-10-09 (`task/OP-008-backup-retention`; offline implementation verified, VM dry run and
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

**Status:** fixed 2026-10-09 — SC-03 on vm-166 opened one incident with two alert occurrences ([step 03](execution/history/OP-011/step-03/evidence.md)) · **Opened:** 2026-10-09 · **Found by:** `conantkd` (T-0022 step 6)

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

**Implementation (2026-10-09, `task/OP-011-correlation`, stacked on `task/T-0024-sc05-disk`).**
`application/correlation.py` (`Correlator`, `CORRELATION_WINDOW` 30 min) is called by `HandleAlertNotification`, so
the webhook and the pull share it. Order: (1) the alert identity is already recorded (an occurrence, or the key that
opened an incident) → `duplicate`; (2) the target's open incident (queued or running) whose last evidence is within the
window, whose alert labels name no other container or dependency, and for which the detectors on a fresh snapshot give
its class (or any class while it is still queued: its own detection reads the same target) → `attached`, audited as
`incident.alert_attached`; (3) else a new incident (`started`). A test that cannot run (stale or unavailable metrics)
never merges. Migration 004 adds `alert_occurrence` (insert-only for the runtime role): the incident's evidence
version is 1 + its attached occurrences and its last evidence time is the newest occurrence, kept out of the incident
body so the worker's full-body writes cannot overwrite them. The intake processes (api, scheduler) now read the
metrics port (`App.metrics`, `wiring.make_metrics`). Not in this fix: resolved alerts (occurrence `status`),
related-incident links, showing the evidence version in the incident view and the run context.

**Step 02 (VMs) and ACR-0004.** Deployed on both VMs; SC-03 still gave two incidents because the first was diagnosed
and closed (31 s) before the second alert was pulled one pass later, although that alert started before the close
([evidence](execution/history/OP-011/step-02/evidence.md)). [ACR-0004](architecture/changes/ACR-0004-correlation-same-episode.md)
(accepted by `conantkd`) adds §6.4 step 3: the target's latest concluded incident of the same class takes an alert
that started at or before it closed (within the window, compatible), with no new run. **Step 03:** deployed on both VMs; SC-03 with the same timing (the second alert pulled after the
first incident closed) gave **one** incident `inc_8a4cf92444ae`, occurrences `started` + `attached`, then
`duplicate` ([evidence](execution/history/OP-011/step-03/evidence.md)).
