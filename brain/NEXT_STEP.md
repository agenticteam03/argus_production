# Next step

**Now (2026-10-20, roll-up, `conantkd`; night work by the agent).**
- **On the VMs:** **both run `main` `bdcd048`** (DEPLOY-195: T-0045 B8, finer link reasons; #195, the redaction fix).
  The UI is built with `VITE_ARGUS_INSIGHTS=1` (DEPLOY-189: B6, the Map and Metrics tabs). Database at migration 007.
  The EVAL-offers leftovers on vm-095 are removed.
- **In review (protected paths, a teammate's approval):**
  - #188 (B7, migration 008);
  - #190 (`gh_json` retries);
  - #193 (B8's `ARCHITECTURE.md` text);
  - #198 (OP-014 step 6, dependency audit; new OP-017, frontend advisories);
  - #199 (OP-014 step 5, ruff and bandit);
  - #200 (OP-014 step 7, actions pinned by SHA).
  The three CI PRs edit different lines of `ci.yml`.
- **Post-merge look asked:** #192 (`config/signals.yaml`, OP-014 step 8) and #195 (the redaction change).
- **Prepared:** the B7 deploy in `task/DEPLOY-B7-B8-prep` (`brain/execution/current/code.bash`; replace `<MAIN>`).

Next, in order:
1. Review the six PRs above.
2. Deploy B7 to vm-095 with the prepared code.bash (008 before the new image, then `argus deploy record`).
3. OP-017: the frontend lane upgrades React Router, then Vite and Vitest.
4. OP-014 step 4 (coverage on changed lines) and the rest of step 7 (`zizmor`, `hadolint`, `shellcheck`).

Below: the rolled-up "next steps" of today's entries, then the 2026-10-19 roll-up.

OP-014 steps 4 to 7 (coverage on changed lines, SAST, dependency audit, workflow linting) need `.github/` changes and
a teammate's review.

Review of #188 (B7), #190 and #193, and a post-merge look at #192 (`config/signals.yaml`) and #195 (redaction). Then
deploy B7 (migration 008 before the new image).

A teammate's post-merge look at the redaction change (safety-relevant, although outside the protected paths). The fix
reaches vm-095 with the next agent deploy (B7 + B8). Property tests for `argus/policy/` in a reviewed PR.

None for this item.

Review; then deploy with B7 (#188): the target service on both VMs and the agent image.

The D.4 click-through in the browser (operator/approver, then viewer). Then the review of #188 (B7) and its deploy:
`db-migrate.sh` (008) before the new image, and `argus deploy record` for the deploy event.

**Now (2026-10-19, roll-up, `conantkd`).**
- **On the VMs:** vm-095 runs `main` `dfa7332` (DEPLOY-176: T-0045 B1 to B5, ACR-0023, migration 007). vm-166 is unchanged (`ccc810e`).
- **On `main`, not deployed yet:** `eae17b9` adds B6 (#184: `/api/v1/target-metrics`, `/api/v1/overview`, ARCHITECTURE 1.8.19) and the B5 follow-up (#185: `db-check` proves 007).
- **In review:** B7 (#188: baseline, the 6h/24h ranges, deploy events, migration 008, 1.8.20). It touches protected paths (`ops/`, `deploy/migrations/`, `contracts/`, `brain/architecture/`), so it needs a teammate's approval.
- **Below this paragraph:** the rolled-up "next steps" of the entries since 2026-10-13. The EVAL-offers, ACR-0021 acceptance, B1 to B6 and DEPLOY-176 ones are done.

Next, in order:
1. **Review #188** (`juanbetancurm` or `juanes6554`).
2. **Deploy `main` to vm-095** with B6 and B7, holding the lease:
   - `db-migrate.sh` (008) before the new image;
   - agent, worker and scheduler on one image;
   - record that deploy with `docker exec argus-v18-agent argus deploy record --commit … --ref main --as …`, since the old image cannot do it;
   - `nonint-check` before and after.
3. **T-0016 frontend** (`juanes6554`) reads the B6 and B7 fields. B8 is optional.
4. **Small items:**
   - a retry in `brain.py`'s `gh_json` for main-guard's occasional `unexpected end of JSON input`;
   - a unit test for #183 (a merge of a branch other than `main` must not keep an approval);
   - on vm-095, remove EVAL-offers leftovers (`/tmp/eo-*`, the `argus-v18-agent:eo-*` images), holding the lease.
5. **#157** (T-0044 RAG, draft): rebase on `main` (it conflicts in `ARCHITECTURE.md`).

Deploy main to vm-095 (B1 to B5, ACR-0023): `db-migrate.sh` (007) before the new image.

B7 (baseline, long ranges, deploy events); the `ARCHITECTURE.md` text of ACR-0021 (§5.8, §7.1, §8.1) now that B1-B4
are merged.

Review of the record PR. When #185 (the `db-check` read that proves 007) and B6 (#184) merge, the next deploy shows
23 checks and the new route.

B6 (#184 target-metrics, then `/api/v1/overview`) and B7. Deploy main to vm-095 (B1 to B5): `db-migrate.sh` (007)
before the new image.

A teammate's approval; then updating an approved pull request with `main` no longer needs a new review.

`juanes6554` reviews the least-privilege part of ACR-0021 and approves this pull request.

B6 (the two new routes) and B7 (baseline and deploy events), after #180 merges.

The team decides ACR-0023 in PR #179. A cause that matches no pattern ("maintenance mode is ON") is still missed.

Merge with both approvals. Then agree with `conantkd` who takes B5 and B6.

B4 (the incident verdict fields). B5 to B7 wait for ACR-0021 to be accepted.

B5 to B7 wait for ACR-0021 to be accepted (new routes, migration 007).

B3 (topology: health, problems, per-dependency links) and B4 (the incident verdict fields).

After the merge, check the push to `main` runs `main-guard` only.

Reviews of #174 (B2), #175 (B3), #176 (B4).

B2 (incident metrics: kind, thresholds, events, window, summary) and B3 (topology health and per-dependency links).

Team review: accept, change or reject ACR-0018, ACR-0019, ACR-0020 and ACR-0022 (second approvals for the safety
principles) and answer the open decisions in the task file. Then phase 15.

Team review of ACR-0021 (second approval: two public routes) and the open decisions in T-0045; then B1.

A teammate reviews (it changes `brain.py` and `REVIEW_PROTOCOL.md`).

A teammate reviews (it changes `.github/`, `brain.py` and `GIT_WORKFLOW.md`); after the merge, open each new task's
pull request as a draft at its first push.

Review of the record PR. Then the follow-ups on the self-merge rule (protect `brain/agents/`, `ops/`, `deploy/*/compose*`
and the write-gate code; check `previous_filename`; restrict who posts `LOCAL CI PASS`).

#156 is merged (`f7df417`). Deploy `main` to vm-095 (`ref=main`) with the usual state probe. Name the two Hobby users in Cloud. Restore vm-166's `argus-lab-cache` in the next vm-166 session.

A teammate reviews and approves this pull request; then `task/TEST-HARDEN-1` (OP-014 steps 1-3).

A teammate reviews; after the merge, redeploy vm-095's agent (both leases), then OP-014 steps 4-8, one PR each.

Review and merge this PR, then redeploy the UI edge on vm-095 (lease, `code.bash`, `nonint-check.sh` before and
after) and do the real-mode click-through with `VITE_ARGUS_INSIGHTS=1`.

Open the PR (`task/T-0016-map-metrics-wiring`), have a teammate review it (ACR-0017 touched a safety principle), then
a person's real-mode login on vm-095 with `VITE_ARGUS_INSIGHTS=1`.

Review (conantkd or juanes6554); juanes6554 connects the frontend.

Merge #160, then this PR (retargeted to main), deploy the agent and the edge on vm-095, then the frontend connection.

PR (reviewer `conantkd` or `juanes6554`), deployment of the agent and the edge on vm-095, then the topology route.

Review of ACR-0016 (juanbetancurm). If accepted: apply ACR-0013 and ACR-0016 to `ARCHITECTURE.md` (the next free version), create the
team's Langfuse Cloud project, LF-3 step 03 on vm-095 (keys, `hosts.env`, worker and agent, one trace, Cloud away),
then remove the stopped self-hosted stack and its volumes. Restore vm-166's `argus-lab-cache` in the next vm-166 session.

Review and acceptance; then the backend PRs (juanbetancurm) and the frontend connection (juanes6554).

Review and merge the redesign PR (fast-track eligible: frontend only, no `.github/` or `contracts/` change, `test`
and `frontend` green). Then the API side decides the two read routes in `frontend/BACKEND-REQUESTS.md` — each needs
an ACR (like ACR-0014) plus a contract update, a sample and an edge allowlist entry — after which the Map and
Metrics tabs light up with no further frontend change.

A teammate reviews/accepts ACR-0015, then implements the design (local Weaviate container, hybrid adapter, embedding
adapter, tests) and runs the TF-IDF-vs-Weaviate recall@3 benchmark on the VM.

Review (conantkd).

Complete full local verification. When the VM leases are available, perform the private stack and canary
sequence in `deploy/langfuse/README.md`, using the Brain code.bash protocol and preserving sanitized evidence.

Obtain teammate review of ACR-0013. In the first implementation PR, update the architecture version/changelog with the implementation, exercise filtered span and exporter-failure tests, and rerun the VM capacity gate in a stable window before enabling permanent tracing.

The OP-008 after-check at the next VM session; the OP-004 timer as a team decision.

Review and accept ACR-0014 in PR #151, apply the exact §7.1 architecture edit and version bump, then merge only
after independent approval and green CI. Run a live Host A/T Prometheus smoke test only with the VM lease.

Its PR when `conantkd` says so (a teammate's approval and the second approval), then the AFTER-MERGE on vm-095 (the
agent and the edge).

vm-095 back to `main` (checkout only) after this PR's merge; a person's browser login on the public UI.

A teammate's acceptance and a second approval; then T-0016 "Level 1 Investigate" as steps (API, edge, frontend, VM).

- A person logs in from a browser and opens an incident.
- The AFTER-MERGE to `main` (#144, approved and merged by `juanbetancurm` at 04:35 UTC, which is ACR-0011's second
  approval; and #145, D-003): vm-095 runs the branch at `8ee48c4` until then.
- One account per person when the team decides.

T-0016: the Playwright acceptance tests and the read-only network guard.

T-0016 step 4 after ACR-0011's second approval: the edge login, the runbooks behind the login, the Nginx image.

A person logs in through `ssh -L 18010` and opens an incident. Then #144's approvals, then 4e with ACR-0011 §8's data.

The approvals of #144 (a teammate's, and the second approval of ACR-0011). Then 4d on vm-095's loopback with the
lease, and 4e once §8's data is known.

A teammate approves (or objects) in the PR.

Next AFTER-MERGE: rebuild the target services on both hosts. A task for evaluation cases with long logs before any
log tool is offered.

PR (reviewer `conantkd`), then the AFTER-MERGE and SC-03, SC-07, SC-08 on the VMs.

A teammate reviews the OP-008 prune list (and the OP-004 timer decision); then one `prune --apply`. T-0041 to
`completed/` in the next roll-up.

A teammate's acceptance and a second approval in the PR; the pending data of ACR-0011 §8; then T-0016 step 4a.

The public-HTTPS ACR (ACR-0011) covers what #137's review saw in a real-mode build: the mock adapter and the
runbooks shipped in the bundle.

Run `npm test` in `frontend/` (and the `vite build`) to close the red/green record, then open the PR. Follow-ups are
unchanged: Playwright acceptance, the read-only network guard, the `contracts/ui-api.json` check, and the new
`offset`/total contract ask for the incident list.

Open the PR for `task/T-0016-step3-screens` (colours, incident page, the crash fix, the test fix) and let CI go green.
Follow-ups unchanged: Playwright acceptance tests, the read-only network guard, the `contracts/ui-api.json` check, and
the incident-list `offset`/total contract ask. The live smoke test still needs the tunnel and a real database login.

PR (reviewer `juanbetancurm`).

The SC-12 expectation (option a), then the roll-up: `IMPLEMENTATION_PLAN.md` row 12 to 100 %.

**Now (2026-10-13, evening roll-up, `conantkd`).** Both VMs run `main` `ad72617` (#113-#131, AFTER-MERGE #132:
migrations 001-006, both Prometheus with the heartbeat rule, heartbeat `alive` on both hosts). #133 (the `platform`
route of a monitoring loss) merged after it: vm-095's scheduler gets it at the next AFTER-MERGE. **Phase 12 is
done:** every scenario five runs (E2E-8 step 2, #134 in review; SC-12 4/5, its miss a correct diagnosis through the
host probe; its expectation follows it in E2E-9, #135 in review). Leases released. The lines below this paragraph are
the rolled-up "next steps" of today's entries: the E2E-8, AFTER-MERGE, T-0035, T-0037, T-0043 and routing ones are done.

Next, in order:
1. Review #134 and #135 (`juanbetancurm`).
2. Offer the new capabilities to their classes, each with evaluation cases (T-0036 histories, T-0037 logs and
   processes, T-0038 baseline, T-0039 prior incidents, T-0040 request path); EVAL-snapshot showed an offer can lower a
   class (0.88 → 0.72), so measure every offer against `main` (0.97, 267/275, EVAL-6).
3. Small open items: OP-004 and OP-008 first `--apply` with a teammate; T-0041 first `db_probe` rotation on vm-166;
   T-0016 Playwright tests; team decisions on the `nginx-slow-check` label and `network.connectivity` networks.

PR (reviewer `juanbetancurm`); the VMs get it at the next AFTER-MERGE.

E2E-8 step 2 on both VMs: `ops/e2e/run.py H-1 H-2 SC-09 SC-11 --runs 5`, then `SC-10 SC-12 ID-1 --runs 5`.

After the merge, on vm-095: one call on a target with closed incidents (from the worker container).

Step 2 done (evidence in `execution/history/T-0037/step-02/`; a trailing colon in command names fixed). Next: the AFTER-MERGE rebuilds the target services; then offer to a class with an evaluation batch.

At the AFTER-MERGE: recreate both Prometheus; `scrape_targets_down` stays 0.

With the AFTER-MERGE on vm-095: the next escalation's notification shows `route: channel:operators`.

After the merge: one call from vm-095's worker on `vm-166/container:argus-lab-api` (its dependency `argus-lab-cache`).

Step 2 done (evidence in `execution/history/T-0038/step-02/`; the 7-day offset replaced by 3 days, inside the retention). Next: offer it to a class with an evaluation batch.

Step 2 done (evidence in `execution/history/T-0036/step-02/`); the network history became the host's. Next: offer the histories to a class with an evaluation batch; decide per-container traffic (cAdvisor network metrics).

E2E-8 step 2 (both leases): `ops/e2e/run.py H-1 H-2 SC-09 SC-11 --runs 5`, then `ops/e2e/run.py SC-10 SC-12 ID-1
--runs 5`; read every miss.

A teammate accepts (or chooses D) in the PR; then the implementation PR.

None for the snapshot in this class. Candidates for the next batch: the metric histories or `search_logs` for the
class whose misses they address.

The snapshot measurement: offer `capture_diagnostic_snapshot` to a class on a branch and compare with this run.

Team decisions: the `nginx-slow-check` root-cause label; whether `network.connectivity` should report each side's
inventory-assigned networks (for `dep-backend-wrong-network`).

After the merge, with the developer: rotate vm-166's `db_probe` token and the agent's copy; `up` stays 1.

T-0035 step 2 on the VMs (both leases): migration 006, the rule on both hosts, the scheduler; measure `updatedAt`
renewal on Alertmanager 0.34.0; then turn the check on.

Open the PR when a reviewer is available.

PR #114 (reviewer `juanbetancurm`); the VMs get it at the next AFTER-MERGE.

Open the PR when a reviewer is available.

**Now (2026-10-13, roll-up, `conantkd`).** Both VMs run `main` `d34f0cb` (#97-#111, AFTER-MERGE #112, from its
evidence; not observed again at this roll-up); `main` after it is Brain only. The task files are up to date:
`tasks/current/` holds only E2E-8, OP-004, OP-008, T-0016 and T-0019.

1. **Review queue (17 PRs, #113-#129, all by `conantkd`):** suggested order #113 (`main-guard` green again), #114 (the
   inspection deny floor), #115, #117, then the rest by number; #120 is stacked on #119. New work by `conantkd` should
   avoid `catalog.py`, `config/policy.yaml`, `executors.py` and `wiring.py` until the capability PRs (#119-#125) merge.
2. **After the merges:** AFTER-MERGE of both VMs to `main` (target services for #114 and #122; agent, worker and
   scheduler together).
3. **Waiting for a teammate:** OP-004 and OP-008's first `--apply` (review of the dry-run counts); ACR-0009 (#116) and
   ACR-0010 (#124).
4. **Team decisions:** the class registry ([D-003](OPEN_PROBLEMS.md)); which class, if any, is offered the tools that
   are offered to no class yet (`get_socket_summary`, the snapshot, T-0036 to T-0040).
5. **E2E-8** (`juanbetancurm`): SC-09 to SC-12 and the identity proof, five runs each. **Open problems:** OP-002
   triage, the OP-003 proposal.

The paragraphs below, down to "**Now (2026-10-12**", are the "Next step" sections this roll-up folded in (newest
first); most are done, and the summary above supersedes them.

AFTER-MERGE of both VMs to `main` once this and #109 are merged.

Measure EVAL-5 and the diagnostic snapshot on vm-095 (needs the lease). Open findings for later tasks: #110 review
(a declared directory matched without a left boundary) and #111 review (`PASS` with every step skipped; gitleaks
scans ignored files without `--pr`).

Use it for the open PRs while GitHub Actions does not run.

After approval and merge: merge `main` into #103 (3b), then #101 (3c; also resolves `T-0019-db-probe.md`, both sections
kept).

A teammate accepts or rejects ACR-0009 in its PR; then T-0035 (implementation, tests first), then its VM proof.

None.

After the merge: AFTER-MERGE of both VMs to `main` (same services). Then batch 3b (host verbs under the 3a policy,
#98). [Evidence](execution/history/T-0019/step-07/evidence.md).

Batch 3b on the VMs (both leases), then the PR; after #98, #101 and this PR merge: AFTER-MERGE of both VMs to `main`.

Offer the snapshot to a class after an evaluation batch; verify on vm-095 with the next AFTER-MERGE.

Measure with the model in the next evaluation batch (nginx: 0.92–0.96 before).

The nginx misses (the upstream not named as root cause) with the next evaluation batch.

`juanbetancurm`: review #97–#103, AFTER-MERGE to `main`, then E2E-8.

None for T-0033.

After 3a is approved and merged: batch 3b (the four host-probe verbs under the policy), then 3c (network verbs).

Read the 8 `health_check_failed` misses run by run (`eval-20261012-182757.jsonl` on vm-095) and decide the wording
question; T-0019 batch 3 (3a in review, 3b, 3c).

**Now (2026-10-12, roll-up, `conantkd`).** Both VMs run `main` `244453b` (#91-#95; observed with `deploy.sh status`
at this roll-up); `main` is `817d88f` (+ #96, Brain only), so the deployment is current. `main-guard` is green again
(#95, the retroactive lines for #91 and #92) and `verify-main` is clean.

1. **EVAL-3 step 2 (vm-095):** the configured model on the 55 evaluation cases, as EVAL-2 did. `restart-sigkill-01`
   is now labelled `no_action_escalated` (RB-008) and is expected to pass where the model escalates.
2. **T-0019 batch 3** (journal, files, process details, `network.connectivity`; the last of Phase 3): first the §4.7
   inspection policy in `config/policy.yaml`.
3. **The Prometheus-down alarm:** T-0032's "not covered" (a watcher from the other host, or a dead-man alert).
4. **Team decisions:** the class registry from EVAL-2's table (keep the model for cpu, blind spot, postgres, disk;
   nginx, dependency, restart loop and health to be decided); the wording checks ("health check"); which class, if
   any, is offered `get_socket_summary`. `restart-sigkill-01` is decided (EVAL-3, #93).
5. **Follow-ups:** `ops/rotate-token.sh` (#94 review): `--rollback` leaves the token `0400` instead of its mode, and a
   failed `docker compose` still prints "recreated"; `db_probe` rotation stays manual. Optional E2E-7 hardening (the
   facts before the model, an explicit unknown cause). Older: OP-002 triage, the OP-003 proposal (ACR-0006), OP-004
   and OP-008 `--apply` after a teammate reviews their previews.
6. **Merged 2026-10-11/12:** #78-#86 (E2E-3 step 2, the 2026-10-11 roll-up, E2E-5, E2E-6, EVAL-1, retroactive lines), #88 (ACR-0007
   accepted), #89 (EVAL-2, ACR-0008), #90 (T-0019 batch 2), #91 (AFTER-MERGE of #88-#90, SC-05 5/5), #92 (OP-012),
   #93 (EVAL-3), #94 (T-0033), #95 (retroactive lines for #91, #92), #96 (T-0033 step 2). Phase 12: SC-01 to SC-08
   all at 5/5.

The paragraphs below, down to "Then (2026-10-11)", are the "Next step" sections this roll-up folded in (newest first);
most are done, and the summary above supersedes them.

The roll-up of 2026-10-11 and 2026-10-12; the Prometheus-down alarm (a watcher from the other host or a dead-man
alert, T-0032's "not covered"); EVAL-3 step 2 in the next model evaluation batch.

**T-0033 step 2** on the VMs after the merge (both leases): rotate vm-166's `host_probe` token and show the
before / refused / recovered reports with the worker's restart count unchanged.

EVAL-3 step 2 with the next evaluation batch (the configured model on the 55 cases).

**OP-012 step 2:** vm-095's agent, worker and scheduler on `main` after the merge.

Optional hardening from the SC-05 research (E2E-7): the facts before the model, an explicit unknown cause. Separately,
the per-step budget counters (a fresh `InvocationContext` per act node) as their own task.

The roll-up of 2026-10-11 and 2026-10-12 (`brain.py rollup`); then T-0019 batch 3 (after the §4.7 inspection policy).

After #89 and this PR merge: AFTER-MERGE on both VMs (checkout `main`, the target services, and agent, worker and
scheduler together). Then T-0019 batch 3 (journal, files, process details, `network.connectivity`), which first needs
the §4.7 inspection policy in `config/policy.yaml`. Open questions for the team: `restart-sigkill-01` (RB-008: exit 137
without OOM — the new kernel OOM records now prove "no kernel OOM kill"), the wording checks ("health check"), and
offering `get_socket_summary` to a class (none needs host sockets yet).

After the merge: the team decides the class registry from EVAL-2's table (keep the model for cpu, blind spot,
postgres, disk; nginx, dependency, restart loop, health to be decided); `restart-sigkill-01` is a RB-008 question
(exit 137 without OOM). The running agent on vm-095 gets the prompt change and ACR-0008 with its next rebuild on
`main` (both leases).

After #82 is approved and merged: rebuild vm-095's agent on main (both leases), then SC-05 × 5.

**E2E-6 step 2:** `ops/e2e/run.py --runs 5 SC-02` on vm-095 (its lease only). Phase 12 then: SC-02's five runs, and
SC-05 after #80 (E2E-5) and vm-095's agent rebuild.

**E2E-5 (proposed 2026-10-11 by `conantkd`; next in the quality lane):** SC-05 is 3/5 after E2E-3. The model knows the
filler has the full filesystem mounted rw, but in the misses it concludes without reading its logs. Proposal: when
`container.status` shows a running container with the flagged filesystem in rw, the next read round (its logs and
resources) is planned by rule; then the model decides. Step 1 is offline (test first); step 2 rebuilds vm-095's agent
and runs SC-05 ×5. Phase 12 now: SC-01, SC-03, SC-04, SC-06, SC-07, SC-08 at 5/5; SC-05 3/5; SC-02 × 5 still to run.
See [the task file](tasks/completed/E2E-5-confirm-writer.md).

**Then (2026-10-11, roll-up, `conantkd`).** Both VMs run `main` `e3286df` (#75-#77), deployed in E2E-3 step 2.
`main-guard` is green again (#72) and `verify-main` is clean.

1. **PR #78 (E2E-3 step 2, Brain only) waits for `juanbetancurm`'s review:** SC-08 5/5, SC-05 3/5. Both SC-05 misses
   saw the filler's rw mount but concluded without reading its logs. It proposes **E2E-5** (a rule-planned
   confirmation read of the suspected writer) as the next quality-lane step and asks whether option 1 or option 2
   (`tasks/completed/E2E-5-confirm-writer.md` arrives with #78).
2. **Phase 12:** SC-01, SC-03, SC-04, SC-06, SC-07, SC-08 at 5/5; SC-05 3/5 (E2E-5); SC-02 × 5 still to run
   (vm-095).
3. **Merged 2026-10-11:** #72 (the exception for #68), #73 (first roll-up), #74 (E2E-2 step 2), #75 (E2E-3 step 1),
   #76 (the roll-up keeps the merge order: this roll-up needed no hand reordering), #77 (SC-08 in the runner
   catalogue).
4. **Open follow-ups:** an alert when a host's own Prometheus is down (T-0032); OP-002 triage and the OP-003 proposal
   (ACR-0006); OP-004 and OP-008 `--apply` wait for a teammate's review of their previews; `disk_pressure` evaluation
   cases; the phase table of `IMPLEMENTATION_PLAN.md` is from 2026-10-05.

The sections below are older and kept for the record; the paragraph above supersedes them. The E2E-3 section just
below was written before its step 2 ran (done, PR #78).

**E2E-3 (2026-10-11):** step 1 is done offline (#75). After the merge, both leases: vm-166 `deploy.sh main` and
rebuild the read-gateway; vm-095 backup, `deploy.sh main`, rebuild agent, worker and scheduler, `argus db check`,
WRITE GATE CLOSED, NO INTERFERENCE; then `ops/e2e/run.py --runs 5 SC-05` on vm-166 (about 55 minutes). See
[the task file](tasks/completed/E2E-3-container-mounts.md).

E2E-2 is done. Pending: [E2E-3](tasks/completed/E2E-3-container-mounts.md), `container.status` reports the
host filesystems a container writes (the SC-05 writer link), then SC-05 ×5 again. Owner open; needs both leases for
its step 2.

**Then (2026-10-10, evening; first roll-up, `conantkd`).** Both VMs run `main` `ebbe9c9` (DEPLOY-MAIN-2); `main` has
moved on to #65–#71. No lease is held.

1. **`main-guard` is red since #68** (merged without an approval of its last push). The fix is PR #72, a retroactive
   line in `policies/main-exceptions.txt`; `juanbetancurm` reviews #68's two last commits there. Merge it first.
2. **E2E-2 step 2 (quality lane, `juanbetancurm`; both leases):** `main` changed `host.disk_usage` and
   `container.status` (#70, #71), so vm-095's agent needs a rebuild: backup, `deploy.sh main`, rebuild agent, worker
   and scheduler, `argus db check`, NO INTERFERENCE; then `ops/e2e/run.py --runs 5 SC-05 SC-07` on vm-166
   ([task](tasks/completed/E2E-2-evidence-gaps.md)). Phase 12 so far: SC-01, SC-03, SC-04, SC-06 at 5/5; SC-05 and
   SC-07 6/10 before E2E-2. SC-02 × 5 when vm-095 is free.
3. **Done today, no deploy needed:** T-0031 (phase 8, the standing write-gate test; `ops/write-gate-check.sh`,
   `--host-only` on a Host T: CLOSED on both VMs); T-0032 (phase 13, Prometheus down on one host escalates that host
   only); T-0030 (phase 13, a Postgres restart is a pause); LANES-1 and LANES-2 (a lease per VM; journal entry files
   and `brain.py rollup`: task branches write `journal/entries/`, whoever merges last runs the roll-up).
4. **Open follow-ups:** an alert when a host's own Prometheus is down (T-0032: `ArgusScrapeTargetDown` runs in that
   Prometheus); `brain.py rollup` orders same-day entries by file name, not merge time (fixed by hand in this
   roll-up); OP-002 triage and the OP-003 proposal (as ACR-0006: ACR-0005 is taken); OP-004 and OP-008 `--apply`
   wait for a teammate's review of their previews.

The sections below are older (2026-10-09 and earlier) and kept for the record; the paragraph above supersedes them.

**LANES-2 (2026-10-10, `juanbetancurm`):** task PRs write `journal/entries/` files instead of editing the logbook,
CURRENT_TEST_STATE and NEXT_STEP; the first roll-up follows this merge. See
[the task file](tasks/completed/LANES-2-journal-rollup.md).

**OP-008 (2026-10-10, `conantkd`):** snapshot-consistent backup, verified markers and preview-first retention are
implemented and dry-run on vm-095 (`VERIFY OK`, 0 sets to remove with `KEEP=7`). Next: a teammate reviews the
preview before any `prune --apply`; scheduling stays a separate team decision. See
[the task file](tasks/current/OP-008-backup-retention.md).

**OP-004 (2026-10-10, `conantkd`):** `argus db prune-checkpoints` (owner-only, read-only preview by default,
transactional `--apply`, audit row) is implemented and dry-run on vm-095: with the 30-day window nothing is eligible
yet (1-day preview: 88 threads). Next: a teammate reviews the counts before any `--apply`; enabling the daily timer
is a separate team decision. See [the task file](tasks/current/OP-004-checkpoint-retention.md).

**Now (2026-10-09, night, `conantkd`). Phase 7 is complete.** Six branches stacked on `main`, each with the previous
one merged in and `main` up to #53: `task/T-0022-alerting` (#45, ACR-0003) → `task/OP-010-reserved-slot` (#46) →
`task/T-0024-sc05-disk` (#47) → `task/OP-011-correlation` (#48, ACR-0004) → `task/T-0026-alert-resolution` (ACR-0005,
migration 005) → `task/T-0027-blind-spot` (the monitoring blind spot class, RB-014). **Both VMs run
`task/T-0027-blind-spot` `c27546f`**; vm-095's database has migrations 004 and 005 (backups
`argus-20261009T131715Z.dump`, `argus-20261009T183857Z.dump`). LAB BASELINE OK, NO INTERFERENCE. Merged today: #49
(ACR-0002 accepted), #50 (T-0025 evaluation), #53 (OP-009, fast-track). #45 waits for `juanbetancurm`'s second
approval (cAdvisor text fixed). #52 (parallel lanes): changes requested (two text suggestions). **Warning for the
team:** `brain.py start` reports `59ffa39` (PR #44, OP-001) merged into `main` without a non-author approval.

1. **PRs, in order:** T-0022 (needs `juanbetancurm`'s second approval: ACR-0003 touches host isolation), OP-010,
   T-0024, OP-011 #48 (ACR-0004), then T-0026 (ACR-0005) and T-0027. After #45 merges, #46 and #47 (no ACR) can
   be retargeted to `main`, updated and merged by fast-track; #48, T-0026 need a re-approval (ACRs). After they merge, both VMs go to `main` (checkout + rebuild of
   the agent image; migrations 004 and 005 are already applied). Do not deploy `main` before: it would drop the monitoring, the
   reserved slot and the correlation (the table can stay; older code ignores it).
2. **Done 2026-10-09:** OP-011 (step 02 showed the second SC-03 alert pulled after the first incident closed →
   ACR-0004; step 03 one incident `inc_8a4cf92444ae`, occurrences `started` + `attached`). T-0024 steps 2-4 (SC-05
   DIAGNOSED; vm-166 keeps the lab filesystem `/srv/argus-lab-fill`, `ops/lab-fill-mount.sh --remove` takes it away).
   T-0022 steps 5-6 and OP-010.
3. **Done 2026-10-09:** resolved alerts (T-0026, ACR-0005, migration 005; [task file](tasks/completed/T-0026-alert-resolution.md)):
   **both VMs run `task/T-0026-alert-resolution` `ea01c68`**; vm-095 has migration 005 (backup
   `argus-20261009T183857Z.dump` before). Its PR goes after #48. **Next code work:** OP-009 is fixed on `task/OP-009-lease-loss`
   (`main` merged in, PR not opened yet); OP-009 before any second worker, OP-004 checkpoint cleanup, SC-06 / SC-08, phase 12 with the
   runner (≥ 5 runs per scenario) and the §21.2 evaluation.
4. **Open question (`conantkd`):** a host incident's scope holds only the host's declared dependents (T-0024 declares
   the filler `depends_on` the host). Opening it to every container of the host (useful for SC-06 CPU) would be an
   ACR (§5 scope rule).

**OP-001 (2026-10-09, `conantkd`):** the 21 runbook `detector` metadata fields and index now match the 20 incident
classes in architecture §1.3 on `task/OP-001-runbook-detectors`. PR #44 passed the local full suite and CI; fast-track
review and merge are next. This metadata update does not enable draft detectors or promote runbooks. See
[the task file](tasks/completed/OP-001-runbook-detectors.md).

**Now (2026-10-09, `conantkd`; read as the state after the T-0020 PR merges):** T-0020 (SC-04,
`postgresql_connection_exhaustion`, RB-004) is done: verified on vm-166 (`inc_075fb0006098` DIAGNOSED). #36 (T-0021)
was merged before its re-review; its fixes and ACR-0002 came in **#39, approved by `conantkd` (second approval of
ACR-0002) and merged**: `main-guard` green, `main` has the fixed launcher. **#40** (T-0023, the scenario runner, with
two reviewer fixes) is merged too. Owed by `juanbetancurm`: ACR-0002's status set to `accepted` (small PR).

1. **AFTER-MERGE T-0020 on vm-166** (checkout only, block in `execution/current/code.bash`). vm-095 may now get
   `main` (it has the fixed launcher and defaults to `mcp`); its agent then gets `postgresql_connection_exhaustion`.
2. Next work: alerting (phase 7, T-0022) and OP-010 (the db-probe's reserved slot) are ready on `conantkd`'s
   branches; OP-009 (before any second worker) is fixed on `task/OP-009-lease-loss`, `main` merged in, its PR next; OP-004 checkpoint cleanup; SC-05 (T-0024); phase 12 with the runner:
   SC-02 and SC-07 × 5, then an SC-04 catalogue entry.
3. **Evaluation (§21.2, `tests/eval/`) and phase 12 (≥ 5 runs per scenario):** §3 "Enablement" enables a class only
   when its evaluation passes. The 4 classes enabled so far (including `postgresql_connection_exhaustion`) are
   enabled ahead of it: they have lab runs, not the §21.2 dataset (≥ 5 labeled cases per class, ≥ 5 trials, compared
   with the deterministic baseline). This is the task that closes that gap.

**Earlier (2026-10-08, `juanbetancurm`):** T-0014 (api / worker / scheduler) is done and verified on vm-095
([evidence](execution/history/T-0014/step-05/evidence.md)); PR #33 merged by fast-track (after-merge review by a
teammate owed). vm-095 is back on `main` `5cdfd98` (checkout only; the images already run this code). vm-166
stays on `task/T-0020-sc04-pg-connections` until that task's PR. Next: **T-0021** (MCP tools process under its own
user, draft PR #36): step 4 (compose) now, step 5 on vm-095 with the lease. Open PRs: #34 (CLI ACT width), #35
(T-0015 step 6 record), #36 (T-0021, normal review: safety model).

**Earlier (2026-10-07, `conantkd`):** T-0019 batch 1 (the db-probe and `database.health`) is deployed on both VMs
from `task/T-0019-db-probe`; its PR waits for review (after PR #29, OP-007, which it includes). After the merge:
AFTER-MERGE (both VMs back on `main`, checkout only). Next: **T-0019 batch 2** (host-probe load, io, top
processes, sockets, directory sizes, kernel OOM records; [task file](tasks/completed/T-0019-db-probe.md)), or
**SC-04** (`postgresql_connection_exhaustion`, RB-004) which now has its probe. Open PRs: #29 (OP-007), #30
(AFTER-MERGE T-0018 record), #31 (OP-008 proposal).

**Next, agreed by `conantkd`: enable more incident classes** (ARCHITECTURE §3 lists 20, 3 are implemented). A class
is enabled only when its detector exists, its runbook is tested in the lab and the §21.2 evaluation passes (§3
"Enablement"); `query_runbook` lets the scenarios exercise the branch runbooks first. Candidates with a scenario
planned: `dns_network_failure` (RB-009, SC-07 exists), `postgresql_connection_exhaustion` (RB-004, SC-04),
`disk_pressure` (RB-005, SC-05), `cpu_saturation` (RB-006, SC-06), `nginx_upstream_failure` (RB-015, SC-08).

**Earlier (2026-10-06):** both VMs on `main` (vm-095 `f126272`, agent image from `2097eb1`; see below).
Merged today: PR #25 (T-0017), PR #22 (T-0015 steps 1-5, **ACR-0001 accepted** by `conantkd`: UIs read-only in this release) and
PR #24 (T-0016 steps 1-2, the mock-driven UI prototype, approved by `juanbetancurm` and `conantkd`). Next for them:
T-0015 step 6 (deploy on vm-095, after it is back on `main`) and T-0016 step 3 (connect the read parts to the API).

**VMs (2026-10-06, `conantkd`):** PR #25 (T-0017) merged by fast-track; vm-095 is back on `main` `f126272`
(checkout only, NO INTERFERENCE). The agent image is still from `2097eb1`: **T-0015 step 6** (`juanbetancurm`)
rebuilds it and proves a read token is refused on `POST`. vm-166 is on `main`. Phase 5 is complete. PR #25 waits
for its after-merge review by a teammate (fast-track rule).

**Handoff (2026-10-05, from `juanbetancurm`; read the latest journal entry first).** In this order:

1. **Review (start of the session, `agents/REVIEW_PROTOCOL.md`):**
   - **PR #8 — OP-005 proposal**, revised with `conantkd`'s requested changes (creation-time guard, scrape-gap
     test) plus one refinement to judge: the young-container branch goes first, so a container recreated under the
     same name counts from zero. Approve or request changes. Do **not** fast-track it.
   - ~~After-merge review of the fast-track PRs #9–#13~~ **done 2026-10-06** (`conantkd`, PR #16): no defects;
     reports posted as comments on each PR.
2. ~~DEPLOY-MAIN~~ **done 2026-10-06** (`conantkd`): both VMs on `main` `09f5ab1`, agent rebuilt, H-1 `HEALTHY`,
   SC-03 verified on LangGraph, NO INTERFERENCE ([evidence](execution/history/DEPLOY-MAIN/step-01/evidence.md)).

**Then — the next tasks:**

| Option | Phase | What | Depends on |
|---|---|---|---|
| ~~T-0014 — worker + scheduler~~ **done 2026-10-08** (`juanbetancurm`, PR #33) | 9 | split the agent into api / worker / scheduler; the worker claims queued incidents and **resumes interrupted runs from their checkpoint**; the scheduler runs periodic checks and pulls firing alerts | T-0013 merged |
| **T-0015 — read access for user interfaces** (`juanbetancurm`) | 10 | read-only tokens, `GET /api/v1/me`, the UI contract: [`tasks/completed/T-0015-ui-read-access.md`](tasks/completed/T-0015-ui-read-access.md) | nothing (starts with ACR-0001 for OD-10) |
| **T-0016 — the web frontend** (`juanes6554`; say *"I want to implement the frontend"*) | 10 | his own framework in `frontend/`, test-driven (the agent writes the tests from his guidelines): [`tasks/current/T-0016-frontend.md`](tasks/current/T-0016-frontend.md) | T-0015 steps 1–5 merged |
| ~~SC-07 — network/DNS scenario~~ **done 2026-10-07** (T-0018, `conantkd`) | 11 | verified on vm-166, twice; RB-009 read via `query_runbook` | — |
| MCP tools child | 4 | tool calls through a separate stdio process under its own user | nothing (independent) |
| *Future:* ACR for UI actions | 10 | give the UI the scope its prototype shows (approvals, starting investigations, simulator, scheduler, health data): a new ACR; approvals touch a safety principle and need a second approval (PR #24 comment, ACR-0001 §5) | the API routes the UI would act on exist (approvals, scheduler T-0014, a health read route) |

**Priority:** T-0015 unblocks `juanes6554`'s frontend (his tests need its contract and sample data); whoever is
free takes it first. Owners above are suggestions.

Two developers can work in parallel on different rows. The VMs are used by one person at a time (`brain.py start`).
