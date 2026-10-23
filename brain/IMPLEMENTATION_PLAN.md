# Implementation plan — Argus v1.8 on two real VMs

**Architecture:** [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) (v1.8.x; changes via ACR) ·
**Environment:** [`infrastructure/environment.md`](infrastructure/environment.md) ·
**Live status:** [`CURRENT_STATE.md`](CURRENT_STATE.md) wins over the status column below.

This plan runs **v1.8 itself on two genuinely separate hosts**: Postgres, separate api/worker/scheduler, the LangGraph
skeleton with checkpointing, the stdio MCP tools child, exact-route gateways and probes, per-host Prometheus, and a
closed write gate (the HITL machinery of §14 is designed, not built: phase 18, OP-015). The current code started as a simplified lab core (SQLite, one process, direct tool
calls); the phases below replace each simplification.

## 1. Phases at a glance (status 2026-10-23, roll-up after #296; phases 0-14 last refreshed 2026-10-13 unless noted)

| # | Phase | What | Why | Status | Next |
|---|---|---|---|---|---|
| 0 | Discovery | facts about both VMs | never assume; protect the existing deployment | ✅ done | — |
| 1 | Project init | v1.8 code layout, tests | a clean, testable core | ✅ 90 % | tidy as later phases touch it |
| 2 | Inventory & identity | `vm-095` / `vm-166` as real hosts | the same name on two hosts must never be confused | ✅ done | — |
| 3 | Target services | read gateway, probes, exporter per VM | Argus reads hosts only through narrow, audited services | ✅ 100 % | T-0019 done: DB probe (batch 1), host-probe verbs (batch 2), the §4.7 inspection policy and the journal / files / processes / network verbs (3a-3c), the deny floor (#114); T-0037 Docker read verbs (#122). On both VMs (`main` `ad72617`). `network.listening_ports` stays a proposal |
| 4 | Tools & guarded execution | every tool call through `InvokeCapability` | policy, audit and host isolation on every read | ✅ 95 % | T-0021 done (#36, #39: reads in an MCP tools process under `argus-tools`, ACR-0002); T-0034 combined capabilities; T-0036 to T-0040 new capabilities merged and deployed, **offered to no class yet** (next: offer each to a class with evaluation cases). T-0047 H5: `analysis.anomaly_summary` offered to `container_restart_loop` only (#274, 2026-10-22; not yet deployed) |
| 5 | Postgres | system of record (incidents, evidence, audit) | durable insert-only evidence; LangGraph checkpoints need it | ✅ 100 % | — (backup/restore drill done 2026-10-06, T-0017) |
| 6 | Runbooks | the library drives recall | diagnoses traceable to a runbook version | ✅ 85 % | recall-quality checks per class: T-0025 measures recall@3 in the §21.2 evaluation (step 1: harness + safety cases; step 2: the baseline and 5 cases per class) |
| 7 | Monitoring & detection | per-host Prometheus, detectors | detect deterministically before any AI | ✅ 100 % | T-0022 (Argus-owned Alertmanager, node-exporter, cAdvisor; alerts pulled, ACR-0003); §6.4 correlation (OP-011, ACR-0004) and resolution (T-0026, ACR-0005); the four detectors: restart loop, health, dependency, **blind spot** (T-0027, RB-014); missing scrape jobs alert (T-0043); the monitoring heartbeat per host (T-0035, ACR-0009). On both VMs 2026-10-13. Open: `disk_pressure` evaluation cases |
| 8 | Policies | scope, limits, closed write gate as data | safety is configuration, not code | ✅ 95 % | escalation routing as data (`routing.yaml`, T-0042; a monitoring loss on the `platform` route, #133); the standing write-gate test in every build and on the VMs (T-0031); the inspection policy and deny floor (T-0019). Open: real routes per family when the team names its channels |
| 9 | Agent workflow | the v1.8 skeleton in LangGraph | resume after a crash; a real worker and scheduler | ✅ 90 % | T-0013 (LangGraph + Postgres checkpoints), OP-006 and T-0014 (lease, `argus api`/`worker`/`scheduler`, a killed worker's run resumed from its checkpoint) done (#33). OP-004 checkpoint cleanup: the approved first `--apply` ran 2026-10-14 (nothing older than 30 days yet). Open: its daily timer (team decision) |
| 10 | Output modes | formatted CLI and `--raw` | readable for humans, complete for developers | ✅ 90 % | ACT result column wraps instead of being cut (fixed 2026-10-07, seen in the SC-07 demo); new scope: read-only web UI (T-0015 API side, T-0016 frontend) |
| 11 | Synthetic incidents | controlled failures on both VMs | proof needs reproducible failures | ✅ 100 % | SC-01 to SC-12 and the identity proof on the VMs: SC-04 (T-0020), SC-05 (T-0024), SC-06 CPU (T-0028), SC-08 nginx (T-0029) included |
| 12 | End-to-end tests | every scenario through the CLI | quality claims need repeated runs | ✅ 100 % | the scenario runner `ops/e2e/run.py` (T-0023): every scenario five runs on the VMs. SC-01 to SC-08 (E2E-1 to E2E-6); H-1/H-2, SC-09, SC-10, SC-11 and the identity proof 5/5, SC-12 4/5 with the miss read (E2E-8 step 2, 2026-10-13, #134 in review; SC-12's expectation follows the host probe, E2E-9, #135 in review). The model evaluation (55 cases × 5 trials) on `main` `d34f0cb`: 0.97 (267/275) after EVAL-6; the capabilities of T-0036 to T-0040 are offered to no class, so they do not change it yet |
| 13 | Failure & recovery | behaviour under real faults | failures become escalations, never crashes | ✅ 95 % | all four faults done on the VMs: worker killed mid-run (T-0014), Postgres restart (T-0030), Prometheus down on one host (T-0032), token rotation without a restart (T-0033); a host's lost monitoring now alarms (T-0035 heartbeat). Open: the first real `db_probe` rotation on vm-166 (T-0041, script merged) |
| 14 | Optional | swap-ability experiments | prove a new executor needs no core change | ⬜ 0 % | `ssh_verbs` executor, only if time allows |
| 15 | Foundations (next phase) | documentation fixes (OP-015, OP-016), `SELF_MERGE_PROTECTED` extended, OP-014 steps 4–8 in CI | green tests must mean "safe" before anything acts | 🔄 ~85 % | [NEXT-PHASE](tasks/current/NEXT-PHASE-supervised-remediation.md) (#170 merged). Done: OP-015, OP-016, `SELF_MERGE_PROTECTED` extended, OP-014 steps 1-7, 10, 12, and 9's mutation runs (policy, read path, redaction: 199 survivors killed, 42 equivalents, no timeout left). Open: OP-014 steps 8, 9's weekly CI job, 11, 13 |
| 16 | Operator access and audit | per-person accounts, WebAuthn, step-up, revocable sessions, permissions, audit chain off-host, private path | an approval or a shell is only as trustworthy as the identity and the record behind it | 🔄 ~70 %: steps 1-3 done and deployed on vm-095 (sessions, revocation, the audit hash chain, EdDSA, WebAuthn and step-up, migration 013; `main` `77c4524`, no key enrolled yet); step 4, the private path, in review (#298); steps 5 (the off-host digest, security alerts) and 6 (exit proof) left | ACR-0018 (`accepted`, #209); [PHASE-16](tasks/current/PHASE-16-operator-access.md) |
| 17 | Cards, catalogue and suggestions | service cards, action cards (code-evaluated preconditions), risk colours, the runbook `actions` block, `suggest_action`, `next_actions`, scenario answer keys | who may touch what and why it should work is reviewed data, not model judgement | ⬜ planned | ACR-0019 (`proposed`) |
| 18 | Supervised actions, offline | §14 tables and nodes, proposals with grounds / prediction / alternatives, basis downgrade, the judge, shadow-mode recording, failure-injection and binding suites against a fake gateway | the machinery exists and is tested before any route | ⬜ planned | ACR-0019 |
| 19 | Approvals and gateway | approvals in the UI (private path, step-up, colours, judge), holds, emergency stop, the action gateway + socket proxy; the worker's dispatch reads only frozen rows (import-boundary and token-isolation tests) | the model never reaches the execution path | ⬜ planned | ACR-0019 |
| 20 | First released action | `container.start` on `vm-166/container:argus-lab-cache` (SC-03), lab only | a reviewed, verified, reversible first write | ⬜ planned | ACR-0019, its own release PR |
| 21 | Operator terminal | broker, SSH CA, per-person accounts, recording off-host, incident linking, card-limited "Insert" | manual repair from the UI, recorded, humans only | ⬜ planned | ACR-0020 (`proposed`) |
| 22 | More autonomous investigation | follow-up checks after any fix, new reads (recent changes, config files, vendor reference corpus), open investigations for unclassified incidents (lab) | investigate more without acting more | ⬜ planned | ACR-0022 (`proposed`) |
| 23 | Isolated research | a research container behind a domain allowlist; a quarantined reader; suggestions for the operator only; disabled by default | outside knowledge without letting the web steer Argus | ⬜ planned | ACR-0022 |
| 24 | Agent skills (developer track) | the team's repeated procedures (`code.bash` blocks, pull request review, ACR version lines, new capabilities, migrations) as reviewed skills in `.claude/skills/` with tested scripts; the runtime keeps its classes and runbooks | the same procedural mistakes recur (#245 merged behind main, PS 5.1 quoting, version-line conflicts) and policy prose alone does not catch them | 🔄 ~80 %: S0-S5 merged (governance, `code-bash-step`, `pr-review`, `acr-and-version-line`, `add-capability`, `db-migration`, `journal-and-task-status`, the vm-deploy checklist, `ui-contract-samples`, S5's first evidence); the runtime track R1 (evaluate the class offers) in progress | [T-0049](tasks/current/T-0049-agent-skills.md) |

**Order of the remaining work (2026-10-13):** offer the new capabilities (T-0036 to T-0040) to their classes, each
with evaluation cases → the evaluation again on `main` → the small open items (OP-004 and OP-008 first `--apply`, the
first `db_probe` rotation T-0041, T-0016's Playwright tests) → 14 only if time allows.

**Next phase (proposed 2026-10-18, not yet approved; juanbetancurm's and conantkd's proposals merged):** 15 → 16 →
17 → 18 → 19 → 20 is the critical path; 21 and 22 run in parallel once 16 is deployed; 23 comes last. Nothing in
16–23 starts before the NEXT-PHASE proposal and its ACRs are accepted.

**Agent skills (proposed 2026-10-21):** 24 runs in parallel and changes no runtime code: S0 governance, then `code-bash-step` and `pr-review`, then the P1 skills. Its runtime steps (R1 evaluate the planned class offers, R2 per-class pre-checks only if they win, R3 runbook diffs from confirmed incidents) and the operator skill (O1, after 16) each wait for their own ACR.

**Scenarios on the real VMs:** every scenario (H-1/H-2, SC-01 to SC-12, the identity proof) five runs through the
runner, NO INTERFERENCE after every run (Phase 12). SC-12 4/5, its miss read (E2E-8 step 2).

## 2. Phase details

Each phase ends with its tests green and `nonint-check.sh` clean on both VMs.

| # | Objective | Components / files | Tests | Expected result | Rollback |
|---|---|---|---|---|---|
| 4 | real reads through `InvokeCapability`, tools in a separate process | `capabilities/*`, `tooling/executors.py`, `tooling/dispatch.py`, `tooling/mcp/{tools_server,client}.py` | observation contract suite; credential isolation (worker UID cannot read tokens); never-another-host; MCP vs direct benchmark (OD-3) | correct attribution for `vm-166/container:x` and `vm-095/container:x` | `TOOL_CATALOGUE=direct` |
| 5 | Postgres system of record | `deploy/migrations/*.sql`, `adapters/outbound/postgres_store.py`, checkpointer | evidence-store contract; runtime role cannot UPDATE/DELETE audit/evidence; backup/restore drill | rows with host, executor, hash | `ARGUS_DB_BACKEND=sqlite` |
| 6 | runbook-driven recall | knowledge adapter, class-to-runbook validation, recall audit | IDs from metadata; conventions pinned; no truncation; unknown runbook refuses startup | passages traceable to a library commit | re-point to a previous commit |
| 7 | per-host detection and alerting | `deploy/monitoring/*`, `config/signals.yaml`, detectors (restart loop, health, dependency, blind spot) | every series has `argus_host`; stale ⇒ undiagnosable | detection reads the target host's own Prometheus | `compose down` monitoring |
| 8 | policy data + engine | `config/policy.yaml`, `config/routing.yaml`, `policy/*` | scope, max-per-incident, level, empty write gate; standing write-gate test | out-of-scope and write attempts refused and audited | revert the data file |
| 9 | the v1.8 skeleton end to end | `orchestration/*` (LangGraph + Postgres checkpointer, §10.1 nodes, strategies), api (JWT), worker loops, scheduler (the HITL machinery moved to phase 18: §14 is designed, not built, OP-015) | component + failure-injection suites (§21.1); crash and resume from checkpoint | healthy ⇒ no model; unsupported ⇒ evidence pack; class ⇒ model loop | redeploy the previous commit |
| 10 | formatted / raw output | `run_event` table, `adapters/inbound/cli/*` | renderer tests from recorded runs | formatted view = real node sequence | — |
| 11 | synthetic incidents | `deploy/lab/*`, `ops/lab.sh` | each scenario starts, is observable, resets; `nonint-check` clean | reproducible on demand | `lab.sh … reset` |
| 12 | end-to-end multi-host diagnosis | `tests/e2e_vms/*` driving the scenarios through the CLI | §4 expectations; SC-01/SC-02 concurrently | correct class, root cause and host in every scenario | — |
| 13 | failure & recovery | worker kill mid-run, Postgres restart, Prometheus down on one host, token rotation | resume from checkpoint; partition ⇒ escalation for one host only | failures are escalations, never crashes or wrong attribution | restart components |
| 14 | swap-ability | `ssh_verbs` executor (forced-command key on vm-166, only with team approval) | executor contract suite unchanged | a new executor kind with zero core changes | remove the key entry |

## 3. Multi-host execution model

| Concept | Across vm-095 and vm-166 |
|---|---|
| Target identity | `TargetRef(host, kind, name)`; the host is part of every key (proposal digest, idempotency key, lock, evidence, audit). `vm-095/container:argus-lab-worker` ≠ `vm-166/container:argus-lab-worker` |
| InventoryPort | `config/inventory.yaml`: vm-095 executors by container name on `argus-v18-core`; vm-166 executors through `argus-v18-tunnel`. The gateways' allowlists are **rendered from the same inventory** (`ops/render_target_config.py`) |
| Executor resolution | `spec.executor` + `target.host` → endpoint → credential `(host, executor)` → client. No endpoint for that host ⇒ refused; **never another host** |
| Guarded execution | validate → budget → audit requested → policy → provider → redact → store evidence → audit result; same path for both hosts |
| Evidence | stores target, host, executor, caller, times and SHA-256; the gateway echoes its own host name — a mismatch is an `upstream_error` (attribution check) |
| Policy | scope = target + inventory neighbours; a read on the other host is refused unless the inventory declares the dependency |
| Persistence | one Postgres on vm-095; every row that names a target carries its host |
| Escalation | recorded notifier (API/CLI); proposals are not offered while the write gate is closed |

Runtime executors are the v1.8 gateways and probes (exact GET routes, typed verbs, per-service tokens). **SSH is the
operator and transport channel, never an Argus executor** (an `ssh_verbs` executor is only the optional Phase 14).

## 4. Ports and networks (as built)

| Service | VM | Host binding | Reached by |
|---|---|---|---|
| `argus-v18-agent` API (humans, Swagger) | vm-095 | `127.0.0.1:18000` | operators via `ssh -L` |
| `argus-v18-postgres` | vm-095 | none | the agent on `argus-v18-core` |
| vm-095 gateway / probes / exporter / Prometheus | vm-095 | none | the agent on `argus-v18-core` |
| `argus-v18-read-gateway` | vm-166 | `127.0.0.1:18701` | the tunnel |
| `argus-v18-host-probe` | vm-166 | `127.0.0.1:18702` | the tunnel |
| `argus-v18-network-probe` | vm-166 | `127.0.0.1:18703` | the tunnel |
| `argus-v18-db-probe` (T-0019; profile `db`) | vm-166 | `127.0.0.1:18704` | the tunnel |
| `argus-v18-prometheus` | vm-166 | `127.0.0.1:18090` | the tunnel |

Networks: `argus-v18-core` 172.30.0.0/24, `argus-v18-mon` 172.30.1.0/24, `argus-lab-app` 172.30.2.0/24,
`argus-lab-iso` 172.30.3.0/24 (SC-07 only, vm-166). Range
18000–18799. Nothing binds to `0.0.0.0` or a public address.

**Cross-host transport — decided and verified 2026-10-01:** a restricted SSH tunnel over port 22, because every other
port between the VMs is filtered and the team cannot change the cloud network rules. On vm-166 the system user
`argus-v18-tunnel` (no shell, no password) may only forward to the five loopback ports above
(`restrict,port-forwarding,permitopen=…`); vm-095 runs the `argus-v18-tunnel` autossh sidecar with a pinned host key.
SSH carries HTTP only, never commands. Reversible: remove the user, the key and the sidecar. Moving to a network rule
later changes only the inventory URLs.

## 5. Non-interference rules

Argus **adds** objects; it never modifies, reuses or depends on objects it did not create.

| Rule | Mechanism |
|---|---|
| N1 Distinct names | `argus-v18-*`, `argus-lab-*`; checked against discovery first |
| N2 Distinct places | `/opt/argus-v18`, optional `/srv/argus-lab-fill`; nothing under other projects' directories |
| N3 Distinct subnets | explicit subnets from unused ranges |
| N4 Distinct ports | the matrix above, verified free |
| N5 No reuse | other deployments' Prometheus, exporters and gateways are never scraped, configured, restarted or relied on |
| N6 No privileged modes | no `privileged`, `network_mode: host`, `pid: host`; only gateways mount their own host's Docker socket |
| N7 Hard limits | `mem_limit` = `memswap_limit`, `cpus`, `pids_limit` on every container |
| N9 Baseline and diff | `ops/nonint-check.sh before/after` around every phase and scenario; any non-Argus difference stops the phase |
| N10 Leftovers | removed only when proven to be ours and unused |
| N11 Kill switch | `docker compose down` per Argus project; nothing else |
| N13 Existing deployment | the protected objects in `infrastructure/environment.md` are never touched |

## 6. Runbook integration (the library lives in `argus/runbooks/`, D-002)

| Topic | Design |
|---|---|
| Source | the reviewed library in `argus/runbooks/` (imported from `agenticteam03/runbooks` at `056b36e`, v1.1.0), shipped inside the agent image; `ARGUS_RUNBOOKS_DIR` can override it |
| Loading | IDs, version and status come from each file's metadata, never the file name; `RUNBOOK-CONVENTIONS.md` is pinned in every context |
| Mapping | `IncidentClassSpec.runbook_ids`; startup refuses a class referencing a missing runbook; draft runbooks shown as `status: draft` |
| Retrieval | TF-IDF over coherent sections; an over-long section is refused, never cut |
| Recorded | the recall audit records runbook ID, version, section, SHA-256 of the section text, library commit |
| Adding knowledge | a new `RB-0xx` in the library + a new pin; a new class = detector + signals + class entry + runbook; **no core change** |

## 7. Synthetic incidents

Hybrid operation: a tiny always-on baseline (vm-166: `argus-lab-api` + `argus-lab-cache` + `argus-lab-db` (testing
only, T-0019); vm-095: the healthy twin
`argus-lab-api`), and every failure started only for its own test, one at a time:
`prepare → start → induce → wait for the signal (readiness gate, not a sleep) → diagnose → verify → reset → nonint-check`.

| ID | VM | Failure | Class · runbook | Expected | Status |
|---|---|---|---|---|---|
| SC-01 | vm-166 | `argus-lab-worker` grows memory to its 64 MiB limit, restart on failure | `container_restart_loop` · RB-001 | OOM by its own limit on **vm-166** | ✅ |
| SC-02 | vm-095 | `argus-lab-worker` (same name!) exits 1, config missing | `container_restart_loop` · RB-008 | non-OOM crash on **vm-095**, not confused with SC-01 | ✅ |
| SC-03 | vm-166 | the cache stops; the api depends on it | `dependency_unavailable` · RB-003/RB-002 | root cause the cache; the api is a victim | ✅ |
| SC-04 | vm-166 | a worker leaks idle-in-transaction sessions on `argus-lab-db` | `postgresql_connection_exhaustion` · RB-004 | root cause the worker | ✅ (T-0020) |
| SC-05 | vm-166 | a filler fills a 256 MiB loop-mounted file to 92 % | `disk_pressure` · RB-005 | fill rate, time to full | ✅ (T-0024) |
| SC-06 | vm-166 | CPU burner capped at `cpus: 0.3` for 3 min | `cpu_saturation` · RB-006 | throttled at quota; vm-095 unaffected | ✅ (T-0028) |
| SC-07 | vm-166 | client on `argus-lab-app`, healthy backend only on `argus-lab-iso` (T-0018) | `dependency_unavailable` · RB-003, RB-009 read via `query_runbook` (its own class `dns_network_failure` later) | network misconfiguration, not a failed service | ✅ |
| SC-08 | vm-166 | nginx → slow upstream with 502s | `http_errors_latency` → `nginx_upstream_failure` · RB-011/RB-015 | upstream exceeds the nginx timeout | ✅ (T-0029) |
| SC-09 | vm-095 | none: "users see stale data" on a healthy api | none → evidence pack | `unsupported_escalated`, **no model call** | ✅ |
| SC-10 | vm-095 | vm-095 exporter stopped | `monitoring_blind_spot` · RB-014 | vm-095 undiagnosable; vm-166 unaffected | ✅ |
| SC-11 | both | requests for another host's target / unknown target | — | refused before any executor call; audited | ✅ |
| SC-12 | vm-166 | vm-166 read gateway stopped | — | vm-166 incidents escalate; vm-095 continues | ✅ |

Simultaneous by design: SC-01 + SC-02 (the identity proof), SC-03 on the baseline, SC-06/SC-10/SC-12 with the other
host's baseline. Quality claims need **≥ 5 runs per scenario** (Phase 12).

## 8. Output modes (real v1.8 stages only)

```text
detect ─▶ recall ─▶ investigate ⇄ act ─▶ … ─▶ record
detect ─▶ evidence_pack ─▶ record          (unsupported / undiagnosable)
detect ─▶ record                           (no_incident)
```

`argus diagnose <target> --reason "…"` (formatted, live), `--raw` (JSON lines of every event), `--check`
(`request_kind=check`), `argus incident <id> [--raw]`. The stages are the graph nodes, never presentation-only.

## 9. Validation checkpoints

| Checkpoint | Proof |
|---|---|
| Non-interference | `nonint-check` clean after every phase and scenario |
| Target identity & multi-host | SC-01 + SC-02 concurrently ⇒ two incidents, two hosts, two diagnoses; SC-11 refusals |
| Inventory & dependencies | SC-03 root cause on a neighbour; startup refuses broken references |
| Executor resolution | reads attributed to the right host; never-another-host test; MCP credential isolation |
| Guarded execution & policy | every call audited; refusals before any network call |
| Classification | SC-09 no model; SC-10 undiagnosable for one host only |
| Evidence & persistence | rows with host/executor/hash; insert-only enforced by roles |
| Runbooks | recall audit with ID, version, section hash, library commit |
| Reasoning | correct diagnoses in SC-01…SC-08 (≥ 5 trials each) |
| Escalation / approval | write-gate standing test green (HITL against a fake gateway: phase 18, OP-015) |
| Output modes | formatted and `--raw` show the same node sequence |
| Recovery | SC-06 (vm-095 unaffected), SC-12, crash/resume |
