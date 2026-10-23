# Current state — the last verified shared state

**As of:** 2026-10-09 (T-0020 SC-04 after #39 and #40 merged, by `conantkd`) · **Architecture:** v1.8.2 (ACR-0002, second approval in PR #39; 1.8.1 ACR-0001) · **Status:** `verified` on
the VMs; T-0013 (LangGraph + Postgres checkpoints) merged and **deployed: both VMs run `main` `09f5ab1`** (§2) ·
shared-Brain setup B1–B8 under way (three developers).

> The VMs are authoritative for what runs there: run `sudo bash /opt/argus-v18/app/ops/deploy.sh status` (or read
> `/opt/argus-v18/DEPLOYED`) and the state probe before trusting this file.

> **Update 2026-10-23 (`conantkd`, OBSERVED with a read-only database check on vm-095):** WebAuthn enrolment tickets were
> issued and keys registered: **`conantkd` 2, `juanes6554` 2, `juanbetancurm` 1** (D3 asks for two; the check's verdict is
> `STOP` until the second key). No privileged permission exists yet. vm-095 still runs `77c4524`; `NO INTERFERENCE`.
> Evidence: [step 03](execution/history/PHASE-16/step-03-enrolment/evidence.md),
> [step 03b](execution/history/PHASE-16/step-03b-keys-check/evidence.md).

> **Update 2026-10-22 (`conantkd`, DEPLOY-77c4524, OBSERVED with `deploy.sh status`):** **vm-095 runs `main`
> `77c4524`**: migration **013** (WebAuthn credentials, challenges, enrolment tickets, step-up tokens; #280), the UI's
> security keys page (#284), the Bearer redaction fix (#278). The relying party is the UI's DNS name (`hosts.env`).
> 49/49 database checks. No key enrolled yet; no privileged permission exists. vm-166 stays on `bdcd048`. Evidence:
> [DEPLOY-77c4524 step 01](execution/history/DEPLOY-77c4524/step-01/evidence.md).

> **Update 2026-10-22 (`conantkd`, DEPLOY-afb72e8, OBSERVED with `deploy.sh status`):** **vm-095 runs `main`
> `afb72e8`**: EdDSA access tokens with the Ed25519 key mounted (phase 16 step 2; every session logged in again),
> `db prune-sessions` (#240; first dry run: 0 sessions), T-0047 H4/H5 (`analysis.anomaly_summary` registered, offered
> to no class), the UI with Vite 8 and the contrast fix (#242, #257). No migration (012). 38/38 database checks. OP-008:
> the approved `prune --apply` removed 18 backup sets (`KEEP=7`). vm-166 stays on `bdcd048`. Evidence:
> [DEPLOY-afb72e8 step 01](execution/history/DEPLOY-afb72e8/step-01/evidence.md),
> [OP-008 step 05](execution/history/OP-008/step-05/evidence.md).

> **Update 2026-10-21 (`conantkd`, T-0047 H2/H3 deploy, OBSERVED with `deploy.sh status`):** **vm-095 runs `main`
> `6c83da3`**: migration **012** `incident_hypothesis` (#236), the hypotheses ranked and stored and shown in the
> incident answer (#237). 38/38 database checks. vm-166 stays on `bdcd048`. Evidence:
> `execution/history/T-0047-H2-deploy/step-01/evidence.md`.
> **Update 2026-10-21 (`conantkd`, T-0046 L5, OBSERVED with `deploy.sh status`):** **vm-095 runs `main` `2324186`**
> with **link recording on** (`link_states`, #234; a restart is no transition, #231): 4 declared container links
> recorded (1 `ok`, 3 `unknown`: scenario owners not running). vm-166 stays on `bdcd048`. Evidence:
> `execution/history/T-0046-L5/step-01/evidence.md`.
> **Update 2026-10-21 (`conantkd`, DEPLOY-A4479DF, OBSERVED with `deploy.sh status`):** **vm-095 runs `main` `a4479df`**
> (phase 16 step 1 #223: sessions, logout, revocation, permissions, the audit hash chain; ACR-0026 #210; ACR-0028
> #222; T-0046 L3 #226 with `link_states` off and L4 #227; T-0047 H1 #228; React Router 7 #229). Database at
> migration **011**; the audit chain starts after 3893 unchained rows. EdDSA off (no key installed). vm-166 stays on
> `bdcd048`. Evidence: `execution/history/DEPLOY-A4479DF/step-01/evidence.md`.
> **Update 2026-10-21 (`conantkd`, DEPLOY-NIGHT, OBSERVED with `deploy.sh status`):** **vm-095 runs `main` `024aa6f`**
> (T-0046 L1 #219, migration **009** `link_event` #220, #221). Database at migration 009. vm-166 stays on `bdcd048`.
> Evidence: `execution/history/DEPLOY-NIGHT/step-01/evidence.md`.

> **Update 2026-10-21 (`conantkd`, DEPLOY-215, OBSERVED with `deploy.sh status`):** **vm-095 runs `main` `b2e3548`**
> (#203: a failed baseline read is not kept; #208's ops scripts). Database still at migration 008. vm-166 stays on
> `bdcd048`. Evidence: `execution/history/DEPLOY-215/step-01/evidence.md`.

> **Update 2026-10-20 (`conantkd`, DEPLOY-B7, OBSERVED with `deploy.sh status`):** **vm-095 runs `main` `999b5bb`**
> (T-0045 B7: the baseline, the 6h and 24h ranges, deploy events); **database at migration 008** (`deploy_event`).
> vm-166 stays on `bdcd048`. Evidence: `execution/history/DEPLOY-B7/step-01/evidence.md`.

> **Update 2026-10-20 (`conantkd`, DEPLOY-195, OBSERVED with `deploy.sh status`):** **both VMs run `main` `bdcd048`**
> (T-0045 B8: finer link reasons, `argus_probe_error` from the exporter on both hosts; #195: a token glued to a
> non-ASCII letter is masked). Database still at migration 007. vm-166 moved from `ccc810e`. Evidence:
> `execution/history/DEPLOY-195/step-01/evidence.md`.

> **Update 2026-10-20 (`conantkd`, DEPLOY-189, OBSERVED with `deploy.sh status`):** **vm-095 runs `main` `2c7248b`**
> (T-0045 B6: `/api/v1/target-metrics` and `/api/v1/overview`; #185's `db-check` read: 23/23). **The UI image is
> built with `VITE_ARGUS_INSIGHTS=1`** for the first time: the Map and Metrics tabs and the Dashboard map are served.
> Database still at migration 007; vm-166 unchanged (`ccc810e`). Evidence: `execution/history/DEPLOY-189/step-01/evidence.md`.

> **Update 2026-10-19 (`conantkd`, DEPLOY-176, OBSERVED with `deploy.sh status`):** **vm-095 runs `main` `dfa7332`**
> (T-0045 B1 to B5: thresholds, heartbeat, chart context, map health and links, the verdict, re-check lineage;
> ACR-0023 log pattern matches). The database is at **migration 007** (`incident.parent_id`). Agent, worker and
> scheduler on one image; vm-166 unchanged (`ccc810e`). Evidence: `execution/history/DEPLOY-176/step-01/evidence.md`.

> **Update 2026-10-18 (`conantkd`, DEPLOY-166, OBSERVED with `deploy.sh status`):** **vm-095 runs `main` `19b1085`**
> (#165 self-merge rule, #166 prompt-injection escape in the agent image; agent, worker and scheduler on one image;
> vm-166 unchanged, `ccc810e`). Its worker exports filtered traces to **Langfuse Cloud (EU)** (ACR-0013 and ACR-0016,
> architecture 1.8.16, connected in LF-3 step 03); the self-hosted Langfuse stack on vm-095 was removed. Evidence:
> `execution/history/DEPLOY-166/step-01/evidence.md` and `execution/history/LF-3/step-03/evidence.md`.
>
> **Update 2026-10-12 late (`conantkd`, roll-up, OBSERVED with `deploy.sh status`):** **both VMs run `main`
> `244453b`** (#91-#95: OP-012, EVAL-3, T-0033), deployed by `juanbetancurm` in T-0033 step 2 after the AFTER-MERGE
> of #88-#90 (`45dda69`). vm-095's agent, worker and scheduler on one image (backup, 20/20 db checks, `phase3_check`
> 55/55, WRITE GATE CLOSED); vm-166 checkout only. vm-166's `host_probe` token was rotated and the agent picked up its
> new copy without a worker restart. LAB BASELINE OK, NO INTERFERENCE. `main` after it (#96) is Brain only. Evidence:
> [`execution/history/T-0033/step-02/evidence.md`](execution/history/T-0033/step-02/evidence.md),
> [`execution/history/AFTER-MERGE-T-0019/step-01/code.bash`](execution/history/AFTER-MERGE-T-0019/step-01/code.bash).

> **Update 2026-10-12 (`conantkd`, T-0019 batch 2 step 03, OBSERVED):** **both VMs run
> `task/T-0019-batch2-host-probe` `040b827`** (batch 2 rebased on `task/EVAL-2-model-trials`, so it also carries
> EVAL-2: ACR-0008, its prompt rule, and batch 2's prompt rule): the target services on both hosts have the six new
> host-probe routes (`/load`, `/io`, `/processes`, `/sockets`, `/directory_sizes`, `/oom`); vm-095's agent, worker and
> scheduler rebuilt together (one image), seven new Level 2 capabilities. `phase3_check` 55/55, `LAB BASELINE OK`,
> NO INTERFERENCE. Back to `main` after #89 and the batch 2 PR merge (AFTER-MERGE, checkout + the same rebuilds).
> Evidence: [`execution/history/T-0019/step-06/evidence.md`](execution/history/T-0019/step-06/evidence.md).

> **Update 2026-10-11 (`conantkd`, E2E-3 step 2, OBSERVED):** **both VMs run `main` `e3286df`** (#75-#77): vm-166's
> read-gateway, host-probe, network-probe and exporter rebuilt (`container.status` shows `host_mounts`); vm-095's
> agent, worker and scheduler rebuilt (backup `argus-20261011T131837Z.dump`, `argus db check` 20/20, WRITE GATE
> CLOSED). LAB BASELINE OK, NO INTERFERENCE. SC-08 5/5, SC-05 3/5. Evidence: `execution/history/E2E-3/step-02/`.

> **Update 2026-10-10 (`conantkd`, DEPLOY-MAIN-2, OBSERVED):** **both VMs run `main` `ebbe9c9`** (#48, #54, #55, #59,
> #60, #62, #42, #51 merged): agent, worker and scheduler rebuilt on vm-095 (`argus db check` 20/20, restarts 0),
> target services and Prometheus rebuilt on both (rules `HttpGatewayErrors`, `ArgusScrapeTargetDown`,
> `ContainerCpuThrottled` loaded). Backup `argus-20261010T124807Z.dump` before. LAB BASELINE OK, NO INTERFERENCE.
> H-1 HEALTHY (`inc_ccfcdf8b5758`). Evidence: `execution/history/DEPLOY-MAIN-2/step-01/`.

> **Update 2026-10-09 (`conantkd`, read as the state after the OP-011 PR merges):** alerts are correlated (§6.4,
> ACR-0004, architecture 1.8.4): an alert on the target and class of an open incident, or of the incident of the same
> episode that already concluded, is attached as an `alert_occurrence` (migration 004) instead of opening another
> incident. Verified with SC-03 on vm-166: one incident `inc_8a4cf92444ae`, two occurrences. Evidence:
> `execution/history/OP-011/step-02/`, `step-03/`.

> **Update 2026-10-08 late (`conantkd`):** vm-166 runs `task/OP-010-reserved-slot` `bc56923` (= T-0020 + T-0022 +
> OP-010): Argus-owned `argus-v18-alertmanager` (127.0.0.1:18091), `-node-exporter`, `-cadvisor`; tunnel account
> `permitopen` 18091; `argus-lab-db` with `reserved_connections=1` (16 ordinary slots, the db-probe has its own).
> LAB BASELINE OK, NO INTERFERENCE. vm-095 runs `task/T-0021-tool-isolation`. Evidence:
> `execution/history/T-0022/step-04/`, `execution/history/OP-010/step-01/`.

## 1. In one paragraph

Argus v1.8 runs on the two VMs. The agent on vm-095 diagnoses incidents on both hosts through the per-host gateways
and probes (vm-166 through the restricted SSH tunnel), stores everything in Postgres, and is read-only. Since T-0013 the
investigation skeleton runs as a **LangGraph graph whose state is checkpointed in Postgres** after every node, so an
interrupted investigation resumes instead of starting over. The remaining work: split the single agent container into
api / worker / scheduler (with recovery of interrupted runs), the MCP tools child, the missing scenarios, alerting
and repeated end-to-end runs.

## 2. What runs (OBSERVED 2026-10-06; code updated 2026-10-12)

| VM | Argus containers | Published ports | Code (`deploy.sh status`) |
|---|---|---|---|
| vm-095 | `argus-v18-agent` (LangGraph runner), `argus-v18-postgres` (healthy), `argus-v18-tunnel`, `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-exporter`, `-prometheus`, `argus-lab-api` | `127.0.0.1:18000` only | `main` `d34f0cb` (2026-10-12, AFTER-MERGE of #97-#111: target services rebuilt; agent, worker and scheduler on one image built from it) |
| vm-166 | `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-db-probe`, `-exporter`, `-prometheus`, `argus-lab-api` (healthy), `argus-lab-cache`, `argus-lab-db` (healthy, testing only) | `127.0.0.1:18701-18704`, `127.0.0.1:18090` | `main` `d34f0cb` (2026-10-12, target services rebuilt) |

- `/opt/argus-v18/app` is a **git checkout** on both VMs (read-only deploy key per VM); the old tarball folder is kept
  as `/opt/argus-v18/app.pre-git-<time>`. Only the agent on vm-095 was rebuilt; the other containers still run the
  code they were started with (same behaviour).
- Agent: `ARGUS_RUNNER=langgraph`, Postgres system of record with migrations `001_init` + `002_checkpoints`;
  `argus db check` **15/15**; OpenAI `gpt-5.6-luna` via the Responses API; runbooks shipped inside the image
  (`argus/runbooks/`, library v1.1.0). `/opt/argus-runbooks/056b36e` on vm-095 is no longer used.
- `/opt/argus-v18/hosts.env` on both VMs; the tunnel target matches it.
- Users: `juanbetancurm`, `conantkd`, `juanes6554` (operator, one shared team password); the old personal user is
  disabled. Login test per user (legacy step 12b.2) **done 2026-10-05**: all three log in and get `outcome: HEALTHY`
  on a `--check` of `vm-095/container:argus-lab-api`.
- Last `nonint-check.sh after`: **NO INTERFERENCE** on both VMs (2026-10-06).
- **Postgres backup proved restorable (T-0017, OBSERVED 2026-10-06):** `ops/db-backup.sh backup` wrote
  `/opt/argus-v18/backups/argus-20261006T185011Z.dump` (11 tables, 4603 rows; folder and files root-only, the dump
  holds password hashes and never leaves the VM); `verify latest` restored it into a throwaway, network-less
  `argus-lab-pgrestore`: `VERIFY OK: 11 tables, 4603 rows match`; the live database was only read. Not scheduled
  yet. Evidence: [`execution/history/T-0017/step-03/evidence.md`](execution/history/T-0017/step-03/evidence.md).
  vm-095's checkout was on `task/T-0017-pg-backup-drill` for the drill; back on `main` `f126272` after the merge
  (AFTER-MERGE T-0017, below).
- **Latest (OBSERVED 2026-10-08, state probe, `conantkd`):** vm-095 runs `task/T-0021-tool-isolation` `a5f330a`
  (deployed by `juanbetancurm`; worker in `mcp` mode, PR #36 changes requested): its agent does **not** carry T-0020
  yet, so `postgresql_connection_exhaustion` is not enabled there until vm-095 runs a commit with T-0020 (`main`
  after #36, or the rollback block R of T-0021 step 5 and then `main`). vm-166 runs `task/T-0020-sc04-pg-connections`
  `b1e7176`: `argus-v18-db-probe` publishes `/metrics` (token), vm-166's Prometheus scrapes it; the SC-04 leaker is
  not running. LAB BASELINE OK and NO INTERFERENCE on both. After PR T-0020 merges: vm-166 back on `main` (checkout
  only).
- **SC-04 (OBSERVED 2026-10-07, T-0020, `conantkd`):** both VMs on `a102bd5` (step 2): the db-probe's metrics,
  the `db_connection_usage` signal, the `DbConnectionsExhausted` alert and the class `postgresql_connection_exhaustion`
  (4 classes). Run 2 on vm-166: the leaker held 16 of 17 usable slots (94 % for 5 min, alert firing);
  `inc_075fb0006098` **DIAGNOSED**, root cause `argus-lab-leaker`, RB-004, `inspect_database_health` read, no database
  restart proposed. Two anonymous volumes left by the leaker's image were removed by ID (approved); the leaker now
  uses a tmpfs. Evidence: [`execution/history/T-0020/`](execution/history/T-0020/).
- **T-0021 (OBSERVED 2026-10-08, step 5, `juanbetancurm`; review fixes deployed in step 5e, PR #39):** vm-095 runs `task/T-0021-tool-isolation`
  `a5f330a` (T-0014 included): the worker runs in `mcp` mode (`ARGUS_TOOL_CATALOGUE=mcp` in `/opt/argus-v18/hosts.env`);
  the 7 executor tokens and their host folders belong to `argus-tools` (uid 10011), so the worker (10010) and the
  api (which now mounts only `db_password`, `jwt_signing_key`, `openai_api_key`) cannot read them; TOOLS ISOLATION
  OK; SC-02 DIAGNOSED through the tools process; OD-3 p95 overhead ~45 ms per read; NO INTERFERENCE. **Do not deploy
  `main` on vm-095 before PR #36 merges** without the rollback first (block R of the evidence): `main`'s api and
  worker would not start (`missing credential`). Evidence:
  [`execution/history/T-0021/step-05/evidence.md`](execution/history/T-0021/step-05/evidence.md).
- **Earlier (OBSERVED 2026-10-08, T-0014 step 5, `juanbetancurm`):** vm-095 runs `task/T-0014-worker-scheduler`
  `169ca07` (migration `003_worker_lease` applied): `argus-v18-agent` runs `argus api`, plus `argus-v18-worker` and
  `argus-v18-scheduler` (no schedule enabled). A worker killed mid-run (SC-02) had its run taken back after the
  lease expired and **resumed from its checkpoint** (`incident.resumed`, DIAGNOSED); a temporary `*/5` schedule was
  submitted once per slot, not resubmitted by a restarted scheduler, and coalesced while its target was busy.
  LAB BASELINE OK, NO INTERFERENCE. vm-166 stays on `task/T-0020-sc04-pg-connections` (not touched). PR #33 merged;
  vm-095 back on `main` `5cdfd98` (checkout only, nothing restarted; LAB BASELINE OK, NO INTERFERENCE). Evidence:
  [`execution/history/T-0014/step-05/evidence.md`](execution/history/T-0014/step-05/evidence.md).
- **Earlier (OBSERVED 2026-10-07, T-0019 batch 1, `conantkd`):** both VMs on `task/T-0019-db-probe` `78afa31`.
  vm-166: `argus-lab-db` (testing only) healthy with the `argus_monitor` role (`pg_monitor`, limit 3),
  `argus-v18-db-probe` on `127.0.0.1:18704`; vm-095: agent rebuilt with `database.health` (Level 3) and the
  `vm-166/db_probe` token; `phase3_check` 33/33; `inspect_database_health` ok; LAB BASELINE OK and NO INTERFERENCE
  on both. Evidence: [`execution/history/T-0019/step-03/evidence.md`](execution/history/T-0019/step-03/evidence.md).
- **Earlier (OBSERVED 2026-10-07, OP-007, `conantkd`):** vm-166 runs `task/op-007-restarting-probe-fix` `9c04e90`:
  the 4 target services rebuilt; a dependency probe now stays while its owner restarts; api -> cache probe 1, no
  series for the absent SC-07 client; `LAB BASELINE OK`, NO INTERFERENCE. Back to `main` after the merge (checkout
  only). Evidence: [`execution/history/OP-007/step-01/evidence.md`](execution/history/OP-007/step-01/evidence.md).
- **Earlier (OBSERVED 2026-10-07, AFTER-MERGE T-0018, `conantkd`):** both VMs on `main` `974d1d7` (checkout only,
  nothing restarted), `LAB BASELINE OK`, NO INTERFERENCE on both. Evidence:
  [`execution/history/AFTER-MERGE-T-0018/step-01/evidence.md`](execution/history/AFTER-MERGE-T-0018/step-01/evidence.md).
- **Earlier (OBSERVED 2026-10-07, T-0018 step 7):** vm-095 runs `task/T-0018-sc07-network` `68d4963`: the agent has
  `knowledge.runbook` (`query_runbook`, in-worker); SC-07 run 2 `inc_21f900ee6139` DIAGNOSED with RB-009 read during
  the investigation; vm-166 stays on `df267ce` (its services did not change). NO INTERFERENCE on both.
- **AFTER-MERGE to main (OBSERVED 2026-10-12):** both VMs `commit=d34f0cb…`, `ref=main` (#97–#111: T-0019 3a/3b/3c,
  the snapshot, EVAL-4/5, the redactor of #110); vm-095 backup, agent/worker/scheduler on one image, 20/20 db checks,
  55/55, WRITE GATE CLOSED; LAB BASELINE OK and NO INTERFERENCE on both. Evidence:
  [`execution/history/AFTER-MERGE-main/step-01/evidence.md`](execution/history/AFTER-MERGE-main/step-01/evidence.md).
- **T-0018 steps 1–5 (OBSERVED 2026-10-07):** both VMs run the checkout of `task/T-0018-sc07-network` (`df267ce`):
  vm-166's 4 target services rebuilt (the container status now carries `networks`; a dependency is probed only
  while its owner runs), vm-095's agent rebuilt from it (the image also carries T-0015 from `main`). H-1 on vm-166
  `HEALTHY`. **SC-07 verified** on vm-166 (`inc_fb92d115abb2`, DIAGNOSED: healthy backend on the wrong network, no
  restart advised); lab reset, `LAB BASELINE OK`, NO INTERFERENCE on both. Back on `main` after the merge
  (AFTER-MERGE block in `execution/current/code.bash`, checkout only). Evidence:
  [`execution/history/T-0018/`](execution/history/T-0018/).
- **Earlier (OBSERVED 2026-10-06, AFTER-MERGE T-0017):** vm-095 `commit=f126272…`, `ref=main`, `LAB BASELINE OK`,
  no restart (agent and postgres kept their uptime), NO INTERFERENCE. `deploy.sh` hints an agent rebuild (T-0015
  step 6). Evidence: [`execution/history/AFTER-MERGE-T-0017/step-01/evidence.md`](execution/history/AFTER-MERGE-T-0017/step-01/evidence.md).
- **Earlier (OBSERVED 2026-10-06, AFTER-MERGE):** both VMs `commit=2097eb1…`, `ref=main`, `LAB BASELINE OK`,
  NO INTERFERENCE; the vm-095 agent rebuilt (image = deployed commit). Evidence:
  [`execution/history/AFTER-MERGE/step-01/evidence.md`](execution/history/AFTER-MERGE/step-01/evidence.md).
- **Deployed code (OBSERVED earlier on 2026-10-06, `/opt/argus-v18/DEPLOYED`):** both VMs `commit=09f5ab1…`, `ref=main`
  (DEPLOY-MAIN). On vm-095 migrations `001_init` + `002_checkpoints` are applied (no new one) and `argus-v18-agent`
  was rebuilt from `main` and runs with `ARGUS_RUNNER=langgraph`; `argus db check` 15/15.
  Evidence: [`execution/history/DEPLOY-MAIN/step-01/evidence.md`](execution/history/DEPLOY-MAIN/step-01/evidence.md).
- **T-0013 step 5 verified 2026-10-05** (by the reviewer `conantkd`): `argus db check` 15/15, H-1 `HEALTHY`, SC-09
  `UNSUPPORTED → escalated`, SC-01 `DIAGNOSED` (RB-001), every run checkpointed in Postgres, NO INTERFERENCE.
  Evidence: [`execution/history/T-0013-review/step-01/evidence.md`](execution/history/T-0013-review/step-01/evidence.md).

## 3. Phase status

See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §1. Done or nearly done: 0, 1, 2, 3, 5, 6, 8, 10.
In progress: 4 (85 %: T-0021 verified on vm-095, PR #36 merged, review fixes in #39), 7 (50 %), **9 (75 %: LangGraph + checkpoints + OP-006 done; api/worker/scheduler split
T-0014 verified on vm-095, PR #33 to merge)**, 11 (70 %: SC-07 done, T-0018; SC-04 done, T-0020), 12 (30 %), 13 (40 %). Not started: 14. Phase 10 (90 %) gets a read-only web UI as new scope:
T-0015 (API side: done; step 6 proved on vm-095 2026-10-07, a read token gets 403 on a write) and T-0016 (frontend: steps 1-2 merged, PR #24,
mock-only); UI actions beyond reading need a future ACR (`NEXT_STEP.md`).

## 4. Scenarios verified on the real VMs

- With the plain runner (2026-10-01/02): H-1/H-2, SC-01, SC-02, the identity proof (SC-01 + SC-02 at once), SC-03,
  SC-09, SC-10, SC-11, SC-12.
- **With the LangGraph runner (2026-10-04):** H-1 (healthy), SC-09 (unsupported → evidence pack), SC-01 (diagnosed,
  RB-001) — every run checkpointed in Postgres.
- **All the plain-runner scenarios now pass on LangGraph (2026-10-06, final `main` agent, one run each):** H-2,
  SC-02, the identity proof, SC-10, SC-11, SC-12 (LGS), plus SC-03 (DEPLOY-MAIN). SC-12 escalates at step 2 (plain
  runner: step 3). Evidence: [`execution/history/LGS/step-01/evidence.md`](execution/history/LGS/step-01/evidence.md).
  Phase 12 still needs ≥ 5 runs per scenario.
- **SC-04 on the LangGraph runner: verified 2026-10-07** (T-0020, one valid run): `postgresql_connection_exhaustion`
  detected from the db-probe metric, RB-004, root cause `argus-lab-leaker`:
  [`execution/history/T-0020/step-03/evidence.md`](execution/history/T-0020/step-03/evidence.md).
- **SC-03 on the LangGraph runner: verified 2026-10-06** on the final `main` code (DEPLOY-MAIN D.5): `DIAGNOSED`,
  root cause `vm-166/container:argus-lab-cache`, confidence high, the api the victim; H-1 `HEALTHY` before (after
  restoring the lab) and after: [`execution/history/DEPLOY-MAIN/step-01/evidence.md`](execution/history/DEPLOY-MAIN/step-01/evidence.md)
  (the 2026-10-05 class demo record: [`execution/history/demo-SC03/step-01/evidence.md`](execution/history/demo-SC03/step-01/evidence.md)).

## 5. Known gaps and decisions pending

- `main-guard` is green: PRs #4 and #9–#13 are recorded exceptions in `policies/main-exceptions.txt`.
- PR #8 (OP-005) was approved by `conantkd` on 2026-10-06 and waits for its author's merge.
- **After-merge reviews of the fast-track PRs #9–#13: all done** by `conantkd` (2026-10-06), no defects. The
  fast-track rule is accepted; the `main-exceptions.txt` header now says fast-track lines are reviewed after the
  merge; OP-006's constants are named (`GraphRunner.FIXED_NODES`, `SAFETY_MARGIN`). **T-0015:** its ACR-0001 pull
  request cannot be fast-tracked (the rule excludes ACRs); its token code should also get a teammate's review.
- **Temporary fast-track until 2026-10-12, and again 2026-10-14 to 2026-10-16:** `juanbetancurm`, `conantkd` and (for the frontend, after onboarding) `juanes6554` may merge their own pull requests under the conditions
  of `agents/REVIEW_PROTOCOL.md` ("Temporary fast-track"); each one is listed in `main-exceptions.txt` and reviewed
  by a teammate after the merge.
- Pending team decision **D-001** (cross-host path and alert direction) and open problems OP-001…OP-003:
  [`OPEN_PROBLEMS.md`](OPEN_PROBLEMS.md).
- Differences between the architecture text and the running system: [`architecture/SUMMARY.md`](architecture/SUMMARY.md).
- **Classes enabled ahead of §21.2:** the 4 enabled classes have lab runs but no `tests/eval/` dataset yet (§3
  "Enablement"); phase 12 and the evaluation close it (`NEXT_STEP.md`). OP-010: the db-probe is blind at 100 %
  connection use.
- An interrupted run is resumed automatically by the worker (T-0014, PR #33 merged). OP-009 (fixed on
  `task/OP-009-lease-loss`): a worker that loses its lease stops the run, so two workers never run the same incident.
- Lab baseline: `deploy.sh status` now ends with `LAB BASELINE OK` or names the stopped/unhealthy `argus-lab-*`
  (DEPLOY-MAIN found `argus-lab-cache` stopped for ~7 h; `nonint-check.sh` does not cover Argus objects).
- vm-095 says "System restart required" — do not reboot (team decision).

## 6. The shared-Brain setup

| Step | State |
|---|---|
| B1–B5 repository, sanitization, Brain, `brain.py`, CI, hooks | done |
| B6 first push, soft review rules (free plan), deploy keys, `ops/deploy.sh` | done (PRs #1, #2; `deploy.sh init` on both VMs 2026-10-04) |
| B7 pilot T-0013 | done (PR #6) |
| B8 teammates | `conantkd` onboarded (PR #3, first review); `juanes6554` pending — his entry is T-0016 (*"I want to implement the frontend"*) |
| B9 retire the private notes | later |
