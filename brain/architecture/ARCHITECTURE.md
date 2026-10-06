# Argus — Production Architecture Specification

**Document type:** consolidated target architecture and implementation blueprint ·
**Version:** 1.8.1 (2026-10-06, ACR-0001; base 1.8.0 of 30 September 2026, sanitized for the shared repository 2026-10-02) · **Audience:** engineers and AI coding agents implementing
Argus from an empty repository.


> **Living architecture — change control.** This file is the source of truth for Argus, and it is not frozen.
> It changes **only** through an accepted Architecture Change Record in `brain/architecture/changes/`
> (process: `brain/architecture/changes/ACR-TEMPLATE.md`). Each accepted change bumps the version (1.8.0 → 1.8.1 …)
> and adds a line to the changelog at the end of this file. Never edit it silently to make an implementation easier.
> Deployment-instance values (§3.6) are reference values; the live environment is `brain/infrastructure/environment.md`.

---

## 0. How to read this document

This is the single architectural reference for Argus. It describes one design. It contains no
alternatives, revision history or migration notes from earlier prototypes.

Statements are labelled by strength:

| Label | Meaning |
|---|---|
| **MUST / MUST NOT** | Architectural requirement. Violating it breaks a safety, correctness or boundary property. |
| **SHOULD** | Strong default. Deviate only with a recorded reason. |
| *Implementation choice* | The team may choose the concrete mechanism; the stated contract still applies. |
| **Open Decision** | Not decided in the source material. Collected in §25. Do not treat as settled. |

Numeric values marked *(default)* are configurable starting values, not proven optima. §21 describes
how they are calibrated.

---

## 1. System overview

### 1.1 What Argus is

Argus is a **general Site Reliability Engineering (SRE) incident-diagnosis and
supervised-remediation agent** for servers and their containerized workloads. It is not built around
one kind of failure. Its core is a fixed safety skeleton. Diagnostic reach grows by *registering*
new incident classes, capabilities and diagnostic strategies (§24), never by redesigning the core.

When a monitoring alert fires, an operator asks, a schedule ticks or a peer agent reports a finding,
Argus does six things:

1. **detects** deterministically, from fresh metrics, whether an incident exists and which registered
   incident class it belongs to;
2. **recalls** similar past incidents and the relevant runbook passages;
3. **investigates** with the diagnostic strategy of that class: a fixed evidence plan, an LLM that
   gathers extra evidence through narrow, read-only capabilities, or a combination of both;
4. **proposes** a remediation, which runs only after policy checks, explicit approval by an
   authenticated human and a re-check just before execution;
5. **verifies** recovery against fresh evidence;
6. **records** the incident, its evidence, every decision and every action in durable, append-only
   audit.

Argus is designed to work alongside a **peer security agent** (§23). The two agents share one incident
model and one trust boundary, so that together they can diagnose different kinds of server problems.

### 1.2 What Argus is not

- Argus is **not the monitoring system**. Prometheus monitors continuously. Argus interprets evidence
  when triggered.
- The LLM **never holds execution authority**. It proposes; deterministic code authorizes; a human
  approves every write.
- Argus is **not a general automation platform**. Remediations are only the write capabilities
  released one by one through the write gate (§13.3). In this release **no write capability is
  released**: Argus is read-only, and remediation is performed by humans.
- Argus is **not the security agent**. Security diagnosis belongs to a peer agent that collaborates
  with Argus through the interface of §23.

### 1.3 Incident classes

An **incident class** describes a *symptom* that the metrics show, not a *cause*. The cause is what the
investigation finds. For example, `container_restart_loop` is a class; "OOM kill", "bad configuration"
and "crashing dependency" are diagnoses within it. This keeps the number of classes small while the
range of diagnoses grows.

Each class is registered as an `IncidentClassSpec` (§5.8): a pure detector, the signals it needs, one
or more runbooks, a diagnostic strategy, the relevant tool tags, budgets and verification signals.

**Runbook library.** Classes are aligned with the Argus runbook library **v1.1.0** (RB-001–RB-021,
source review 2026-09-29; index: `RunbooksLab/RUNBOOK-INDEX.md`). Every runbook in it is **draft**
(`last_tested: null`). A runbook reached as a *branch* is retrieved when the investigation of the parent
class points to that cause.

| Family | Class | Runbook(s) | Branch runbooks | Strategy |
|---|---|---|---|---|
| stability | `container_restart_loop` | RB-001 (OOM cause), RB-008 (non-OOM cause) | — | `model_loop` |
| availability | `health_check_failed` | RB-002 | RB-003, RB-015 | `plan_then_reason` |
| availability | `http_errors_latency` | RB-011 | RB-015, RB-016, RB-021 | `model_loop` |
| availability | `nginx_upstream_failure` | RB-015 | RB-002, RB-003 | `plan_then_reason` |
| availability | `tls_failure` | RB-016 | — | `plan_then_reason` |
| dependency | `dependency_unavailable` | RB-003 | RB-004, RB-009 | `model_loop` |
| dependency | `dns_network_failure` | RB-009 | — | `plan_then_reason` |
| saturation | `cpu_saturation` | RB-006 | — | `model_loop` |
| saturation | `host_memory_pressure` | RB-007 | RB-001 | `model_loop` |
| saturation | `disk_pressure` | RB-005 | RB-019 | `model_loop` |
| saturation | `disk_io_saturation` | RB-010 | — | `model_loop` |
| saturation | `fd_socket_exhaustion` | RB-012 | — | `model_loop` |
| database | `postgresql_connection_exhaustion` | RB-004 | RB-013 | `model_loop` |
| database | `postgresql_blocking` | RB-013 | — | `model_loop` |
| database | `postgresql_storage_pressure` | RB-019 | RB-005 | `model_loop` |
| platform | `docker_daemon_unavailable` | RB-017 | — | `plan_then_reason` |
| platform | `clock_drift` | RB-020 | — | `plan_then_reason` |
| platform | `monitoring_blind_spot` | RB-014 | — | `evidence_pack` |
| change | `deployment_regression` | RB-018 | — | `model_loop` |
| cross-system | `cascading_overload` | RB-021 | RB-006, RB-007, RB-011 | `model_loop` |

- **Enablement.** A class is enabled in the registry only when its detector exists, its runbook has been
  promoted under the library's rules (fault-injection cases, fresh verification, reviewer, actual
  `last_tested`), and the §21.2 evaluation passes for it. `cascading_overload` additionally requires
  the core classes to be validated first (RB-021).
- **Remediation.** The runbooks' mutating actions are candidate write capabilities. In this release
  **none is released**: they are carried out by the owning humans, and Argus contributes evidence and
  diagnosis. Hard constraints from the runbooks hold whatever is released later, for example **never
  restart the dependent service** (RB-003) and **never restart a victim** (RB-002).
- **Stale or missing metrics** end as `undiagnosable` (§9); the escalation references RB-014.

Later families and the security agent's own classes are added the same way.

**No matching class.** Three situations are kept apart:

| Situation | Outcome | Model call |
|---|---|---|
| Nothing is wrong: no registered detector fires and no alert is firing | `no_incident`, closed, no escalation | no |
| Something is reported (an alert fires, or a human or peer reports a problem) but no registered class matches | `unsupported_escalated`: Argus runs the fixed **evidence pack** (§10.7), then escalates to the routing target of §15.2. **No diagnosis is claimed.** | no |
| A class matches, but the evidence does not support a diagnosis | the strategy escalates, or the budget runs out ⇒ escalation | yes |

Every unsupported incident is stored with its alert, snapshot and evidence pack, and counted per alert
name (§18.2). That list is the backlog of classes to register next, and those stored incidents become
their first evaluation cases (§21.2).

Every Prometheus alert rule that routes to Argus **SHOULD** correspond to a registered class. An alert
without one is handled as unsupported.

### 1.4 Non-negotiable rules

1. The LLM may propose an action; it never has the authority to execute it.
2. **No write capability ever executes without the explicit approval of an authenticated human.** This
   holds for every trigger, every strategy and every caller, including peer agents.
3. A peer agent never holds write authority. It may request an investigation or contribute evidence;
   it never approves.
4. Every capability invocation passes through one guarded entry point (`InvokeCapability`, §12.4). No
   caller reaches a capability any other way.
5. A refusal is an observation, not a crash.
6. A trigger starts an investigation; it never bypasses detection or safety.
7. No diagnosis is claimed for an incident that matches no registered class.
8. A successful command is not recovery until fresh evidence confirms it.
9. A human approves one frozen proposal, not an intention. Any change needs a new approval.
10. When Argus cannot tell whether an action happened, it escalates to a human instead of acting again.
11. Audit may never be skipped. Telemetry may be dropped.

### 1.5 Glossary

| Term | Meaning |
|---|---|
| **Host A** | Agent server: Argus API, worker, scheduler, Argus Postgres |
| **Host T** | A target + monitoring server: workloads, Prometheus, Alertmanager, exporters, gateways, probes. The design allows several; the first deployment has one, logical name `host-t` |
| **Trigger** | Anything that starts an investigation: alert, manual request, schedule tick, reconciliation, peer finding |
| **Incident** | Argus's unit of work; identified by a ULID `IncidentId`, which equals the LangGraph `thread_id` |
| **Incident class** | A registered symptom with a pure detector, required signals, runbook, strategy and budgets (§5.8) |
| **Capability** | A named operation that can be requested, e.g. `network.tcp_connect`, `container.restart` |
| **Executor** | A named kind of backend that carries out capabilities (`docker_read`, `host_probe`, `prometheus`, …). The target's host selects the concrete instance through the inventory (§12.3) |
| **Tool provider** | A source of capabilities for the catalogue: the MCP tools child, the in-worker provider, later an external tool server (§12.5) |
| **Diagnostic strategy** | A registered way of investigating one incident: it returns decisions and never executes anything itself (§10.3) |
| **Evidence pack** | The fixed, model-free set of Level 1 observations collected for an unsupported incident (§10.7) |
| **Evidence record** | One stored, redacted, insert-only observation, referenced everywhere by ID and hash (§5.4) |
| **Inventory** | The data describing hosts, targets, dependencies, executor endpoints and allowlisted endpoints/paths (`InventoryPort`, §8.1) |
| **Principal** | An authenticated caller: a human, a service or a peer agent, with a role and scopes (§5.2) |
| **Peer agent** | Another agent, such as the security agent, that collaborates with Argus through §23 |
| **Target hold** | A marker that forbids write actions on a target, e.g. to preserve forensic evidence (§13.5) |
| **Port** | A deterministic outbound dependency interface owned by Argus |
| **Driving adapter** | An inbound entry point that invokes an application use case |
| **Proposal** | An immutable, digest-identified description of one write action awaiting approval |
| **Write gate** | The deployment-level control that keeps each write capability impossible until its release criteria in §22.2 pass |

---

## 2. Architectural style and code organization

### 2.1 Style

Argus uses a **hexagonal (ports and adapters)** architecture around a framework-free domain. The core
is a **fixed safety skeleton**: triggers, detection, the guarded capability entry point, policy,
approval, the action ledger, verification and audit. Everything that makes Argus diagnose *more* is
**registered** around that skeleton, so growth never edits it.

There are five separate extension mechanisms, and they **MUST NOT** be conflated:

| Mechanism | Answers | Examples |
|---|---|---|
| **Application use case + driving adapter** | "The outside world starts or queries Argus." | Alertmanager webhook, manual HTTP/CLI, scheduler, peer-agent adapter |
| **Port + adapter** | "Argus code deterministically needs this dependency." | Metrics, LLM, knowledge, memory, audit, notification, inventory |
| **Capability under policy** (served by a tool provider, optionally over MCP) | "Someone asked for this named operation. Is it permitted?" | logs, inspect, probes, metric history, restart |
| **Incident class** | "Which symptom is this, and how is it investigated?" | `container_restart_loop`, `disk_pressure` |
| **Diagnostic strategy** | "In what order is evidence gathered and judged?" | `evidence_pack`, `model_loop`, `plan_then_reason` |

Rule of thumb: **the outside world starts a use case; our code calls a port; a strategy requests a
capability through the guarded entry point; a class decides which strategy runs.**

### 2.2 Packages and responsibilities

| Package | Responsibility | MUST NOT |
|---|---|---|
| `argus/domain` | Vocabulary: incidents, triggers, principals, targets, inventory values, incident-class and capability descriptors, observations, evidence records, decisions, proposals, approvals, holds, actions, audit records | import frameworks or perform I/O (Pydantic is allowed only for trust-boundary value models) |
| `argus/application` | Use cases, `InvokeCapability`, correlation, idempotency, scheduling policy, read models, the `InvestigationRunner` and `ToolCatalogue` Protocols | import LangGraph, FastAPI, the MCP SDK or concrete adapters |
| `argus/detectors` | Pure functions: fresh `MetricSnapshot` → finding or healthy; the incident-class registry | do I/O, read the clock or call a model |
| `argus/policy` | Evaluation engine for the policy data file: allowlist, target scope, read/write class, risk, approval requirement, approver scope, per-incident limits, holds, write gate, remediation options | be delegated to the model or MCP; import anything but `domain`; contain the policy *rules* themselves (those are data, §13.1) |
| `argus/orchestration` | LangGraph skeleton, nodes, routers, state, context assembly, action ledger logic, `InvestigationRunner` implementation, checkpointer selection | import MCP SDK/`tooling/mcp` or concrete adapters |
| `argus/orchestration/strategies` | Registered diagnostic strategies (§10.3) | call capabilities, ports with side effects, the database or gateways; they only return decisions |
| `argus/capabilities` | Capability specs and implementations; typed `Observation`; redaction; the write-capability contract | decide authorization; read configuration directly; write audit |
| `argus/tooling` | Model-tool harness, `ToolCatalogue` aggregate and tool providers, `ExecutorRegistry`, MCP client/server adapters, dispatcher, local write dispatch | contain domain policy; become a second source of capability truth |
| `argus/ports` | Seven deterministic outbound dependency Protocols + provider-neutral value contracts | contain business logic |
| `argus/adapters/inbound` | HTTP (FastAPI) incl. authentication, CLI, Alertmanager translation, peer-agent adapter | contain domain rules |
| `argus/adapters/outbound` | Prometheus, model provider, knowledge, stores, inventory, notifiers, and their fakes | import one another |
| `argus/infrastructure` | Typed settings, DB access, composition root (`wiring.py`), worker and scheduler bootstraps | be imported by `domain` or `application` |
| `argus/observability` | Metrics, structured logging, optional tracing | hold audit records; become an application port |

### 2.3 Dependency rules (enforced by import-boundary tests from the first commit)

1. `domain/` imports no project or framework modules (Pydantic excepted, see §2.2).
2. `detectors/` imports `domain` only.
3. `ports/` contains Protocols and provider-neutral value types only.
4. `application/` imports `domain`, `ports`, `policy` and its own `InvestigationRunner` and
   `ToolCatalogue` Protocols. It **never** imports LangGraph, FastAPI or MCP.
5. `orchestration/` imports `domain`, `ports`, `policy`, `detectors` and LangGraph, and implements
   `InvestigationRunner`. It receives the model-tool harness and `InvokeCapability` by constructor
   injection. It never imports `tooling/mcp/` or concrete adapters.
6. `orchestration/strategies/` imports `domain` only, and receives the harness by injection. A
   strategy returns decisions; it never executes them.
7. `policy/` imports `domain` only.
8. `capabilities/` may use `httpx`/Docker client libraries. It never imports `application`,
   `orchestration` or `policy`. Combined capabilities receive an invoker bound to `InvokeCapability`
   by injection; they never call another capability or executor directly.
9. **Only `application/invoke_capability.py` calls `ToolCatalogue.call`**, and only
   `orchestration/nodes/execute_write` calls `tooling/local_write.py`. An import/call-site test
   enforces both.
10. `tooling/mcp/` is the **only** location of the MCP SDK for the tools server and client.
11. `tooling/model_harness.py` depends on `LLMPort` and `ToolCatalogue`. It converts MCP schemas and
    results into `ModelToolDefinition` and `Observation`.
12. `adapters/outbound/` import `ports` and `domain`; adapters never import other adapters.
13. `adapters/inbound/http/` is the only FastAPI location. `adapters/inbound/agent/` is the only
    location of the peer-agent listener.
14. `infrastructure/wiring.py` is the **only** module that assembles concrete adapters, the runner, the
    harness, the catalogue, the tool providers, the executor registry and the MCP transport.
15. `infrastructure/scheduler.py` is a driver only. It never calls detector, model or graph internals.
16. No environment-specific or host-specific conditionals outside `infrastructure/settings.py`,
    `wiring.py`, the inventory and policy data files, and `deploy/`.

```mermaid
flowchart TD
    INB["Driving adapters: HTTP / CLI / scheduler / peer agent / worker loops"] --> APP[application]
    APP --> DOM[domain]
    APP --> PORTS[ports]
    APP --> POL[policy]
    APP --> IR["InvestigationRunner Protocol"]
    APP --> INV["InvokeCapability (guarded entry point)"]
    INV --> CAT["ToolCatalogue (aggregate of providers)"]
    ORCH["orchestration skeleton + LangGraph"] -->|implements| IR
    ORCH --> DOM
    ORCH --> PORTS
    ORCH --> POL
    ORCH --> DET[detectors + class registry]
    ORCH --> STRAT["strategies (return decisions only)"]
    ORCH -->|injected| INV
    STRAT --> HARNESS["model-tool harness (injected)"]
    DET --> DOM
    POL --> DOM
    OUT[adapters/outbound] --> PORTS
    WIRE["infrastructure/wiring"] --> OUT
    WIRE --> ORCH
    WIRE --> HARNESS
    WIRE --> CAT
    CAT --> TOOL["tooling/mcp (stdio child)"]
    CAT --> LOCAL["in-worker provider"]
    TOOL --> EXEC["ExecutorRegistry → capabilities"]
    LOCAL --> EXEC
    APP -. never .-> ORCH
    ORCH -. never imports .-> TOOL
    STRAT -. never calls .-> CAT
```

### 2.4 Repository layout

```text
argus/
├── domain/
│   ├── incident.py              Incident, IncidentId (ULID), IncidentStatus, IncidentOutcome
│   ├── trigger.py               InvestigationRequest, TriggerKind, TriggerOccurrence
│   ├── principal.py             Principal (human | service | agent), roles, scopes
│   ├── alert.py                 AlertNotification, Fingerprint, AlertOccurrence (vendor-neutral)
│   ├── target.py                TargetRef (host, kind, name), target-kind registry
│   ├── inventory.py             HostInfo, TargetInfo, dependency graph values
│   ├── incident_class.py        IncidentClassSpec, DetectorResult
│   ├── decision.py              AgentDecision union, InvalidDecision, ApprovalDecision
│   ├── action.py                ActionProposal (+digest), Approval, ResumeIntent, ActionRecord, ActionState, TargetHold
│   ├── observation.py           MetricSnapshot, Passage, Observation, EvidenceRecord, EvidenceRef
│   ├── audit.py                 AuditRecord, AuditCategory
│   └── errors.py
├── application/
│   ├── handle_alert.py          HandleAlertNotification
│   ├── run_investigation.py     RunInvestigation (manual/scheduled/system/peer normalization + intake)
│   ├── invoke_capability.py     InvokeCapability: the single guarded entry point to every capability
│   ├── answer_approval.py       AnswerApprovalRequest (authenticated, scoped, digest-bound, atomic)
│   ├── holds.py                 PlaceTargetHold, ReleaseTargetHold
│   ├── resume_answered.py       ResumeAnsweredApprovals (worker-internal)
│   ├── deliver_notifications.py DeliverNotifications (worker-internal)
│   ├── reconcile_alerts.py      ReconcileFiringAlerts (scheduler-driven, optional)
│   ├── get_incident.py          GetIncident, ListIncidents, ListPendingApprovals (role-redacted views)
│   ├── verify_recovery.py       fresh-sample verification logic
│   ├── correlation.py           window + compatibility test + evidence_version + related incidents
│   ├── scheduling_policy.py     skip-if-active, max queued age, concurrency/cost ceilings, principal quotas
│   ├── investigation_runner.py  InvestigationRunner Protocol (no LangGraph import)
│   ├── tool_catalogue.py        ToolCatalogue Protocol
│   └── ports.py                 inbound use-case Protocols and read models
├── detectors/
│   ├── <class>.py               one pure detector per class of §1.3 (container_restart_loop.py, …)
│   └── registry.py              the IncidentClassSpec list (class → detector, signals, runbooks, strategy, …)
├── policy/
│   ├── engine.py                loads and validates the policy data file; policy_version = SHA-256
│   ├── checks.py                policy.check(capability, args, incident, caller) → PolicyDecision
│   ├── scope.py                 target scope rules, incident scope from the inventory
│   ├── inspection.py            per-target inspection policy (allowed paths, denied patterns)
│   ├── remediation_options.py   policy-generated proposal choices
│   ├── approvers.py             approver scope rules
│   ├── holds.py                 target-hold evaluation
│   └── write_gate.py            deployment write gate per (capability, target); default closed
├── capabilities/
│   ├── registry.py              canonical name → implementation + spec; startup validation
│   ├── spec.py                  CapabilitySpec
│   ├── write_contract.py        WriteCapability contract (identity, dispatch, reconcile, verification)
│   ├── result.py                Observation construction, truncation
│   ├── redaction.py             Redactor applied to every evidence source
│   ├── container/               status, resources, logs, health, events, processes, network, files, restart (write)
│   ├── host/                    cpu, memory, disk, load, io, uptime, top processes, directories, journal
│   ├── network/                 dns, tcp, http, connectivity, sockets
│   ├── database/                database health (via db-probe)
│   ├── metrics/                 history tools over named signal templates (Prometheus)
│   ├── knowledge/               query_runbook, query_prior_incidents (in-worker)
│   ├── analysis/                combined tools: diagnostic snapshot, timeline, request path, baseline
│   └── fakes/                   deterministic doubles, one per area
├── orchestration/
│   ├── graph.py                 the fixed skeleton: node/edge definitions
│   ├── nodes/                   detect, recall, investigate, act, propose_action, request_approval,
│   │                            await_approval, precheck_action, execute_write, verify, record
│   ├── strategies/              evidence_pack, model_loop, plan_then_reason; registry
│   ├── state.py                 graph state (Argus-owned values and evidence references only)
│   ├── context.py               ContextAssembler
│   ├── prompts.py               system instructions template
│   ├── action_ledger.py         precheck, ledger transitions, attempting reconciliation
│   ├── runner_langgraph.py      implements application.InvestigationRunner
│   └── checkpointer.py          Postgres saver (SQLite only in local tests)
├── ports/
│   ├── metrics.py  llm.py  knowledge.py  memory.py  audit.py  notification.py  inventory.py
├── adapters/
│   ├── inbound/
│   │   ├── http/  app.py auth.py alerts.py investigations.py approvals.py incidents.py holds.py alertmanager.py
│   │   ├── agent/               peer-agent adapter (reserved, §23)
│   │   └── cli/
│   └── outbound/
│       ├── metrics_prometheus.py   metrics_fake.py
│       ├── llm_openai.py           llm_mock.py
│       ├── knowledge_tfidf.py      knowledge_fake.py
│       ├── memory_postgres.py      memory_sqlite.py   memory_fake.py
│       ├── audit_postgres.py       audit_jsonl.py     audit_recording.py
│       ├── inventory_yaml.py       inventory_fake.py
│       └── notify_slack.py         notify_email.py    notify_recording.py
├── tooling/
│   ├── model_harness.py         ModelReply → AgentDecision; binds tool + decision definitions
│   ├── catalogue.py             ToolCatalogue aggregate over tool providers
│   ├── providers/               mcp_child.py (target-side reads), in_worker.py (Argus-internal reads)
│   ├── executors.py             ExecutorRegistry: executor name → client class
│   ├── mcp/
│   │   ├── client.py            stdio MCP client adapter
│   │   └── tools_server.py      stdio-only read-tools MCP server
│   ├── dispatch.py              canonical capability dispatch + executor resolution
│   └── local_write.py           write dispatch (never MCP)
├── infrastructure/
│   ├── settings.py  wiring.py  db.py
│   ├── worker.py                intake claim/recovery; resume-intent, outbox and expiry loops
│   └── scheduler.py             cron-style RunInvestigation / ReconcileFiringAlerts driver
├── observability/
│   ├── metrics.py  logging.py  tracing_langfuse.py  tracing_noop.py
└── runbooks/                    reviewed copy of the runbook library v1.1.0: RB-001-….md … RB-021-….md
                                 + RUNBOOK-CONVENTIONS.md (shared contracts, pinned in context)

frontend/                        the team's web UI: its own toolchain; talks to the HTTP API only (ACR-0001)

config/
├── inventory.yaml               hosts, executor endpoints, targets, dependencies, allowlisted endpoints/paths
├── policy.yaml                  allowlist, target rules, inspection policy, approver scopes, write gate, holds rules
├── signals.yaml                 signal name → PromQL template (detection, verification and history tools)
└── routing.yaml                 escalation routing per class family (human channel or peer agent)

deploy/
├── compose.host-a.yml           argus-api, argus-worker, argus-scheduler, postgres
├── compose.host-t.yml           Argus-owned monitoring, gateways, probes (and lab workloads when used)
├── compose.dev.yml              both hosts emulated locally
├── prometheus/  alertmanager/   Argus-owned monitoring configuration and alert rules
├── firewall/                    host firewall rules for the private cross-host path (§3.2)
├── docker-gateways/             read gateway ACLs; action gateway service
├── probes/                      host-probe, network-probe, db-probe images/config
├── scheduler/                   schedules.yaml
└── migrations/                  SQL schema migrations (schema-owner credentials)

tests/
├── unit/  contract/  component/  e2e/
├── security/                    import boundaries, single entry point, gateway routes, auth, approval
│                                binding, GetIncident authz, prompt injection, redaction, MCP identity,
│                                write gate, holds, peer scope
├── failure_injection/           crash points of §14, fast answer, scheduler overlap, late evidence
├── integration/                 real Prometheus/Postgres/gateways/probes/MCP/model (marked)
└── eval/                        labeled incident set per class, unsupported cases, baseline, thresholds.yaml (marked)
```

*Implementation choice:* file names inside a package may change, but package boundaries and the
dependency rules may not.

---

## 3. Deployment topology

### 3.1 Hosts

Argus runs on its **own agent host (Host A)**, separate from every host it diagnoses. The first
production deployment has **exactly two servers**:

| Host | Runs | Rationale |
|---|---|---|
| **Host A — Agent** | `argus-api`, `argus-worker`, `argus-scheduler`, `postgres` (Argus state) | Argus and its incident history survive failure of the target host. An agent that dies with the host it is diagnosing cannot report on it, and resource exhaustion on the target host is a primary scenario. |
| **Host T — Target + Monitoring** (logical name `host-t`) | monitored workloads, Argus-owned `prometheus` and `alertmanager`, `argus-exporter`, `docker-read-gateway`, `host-probe`, `network-probe`, `db-probe`; `action-gateway` only after a write capability is released | Monitoring stays beside what it observes. Target-side probes observe the target's real host and network context. |

More monitored hosts are added as further Host T instances: inventory entries (§5.8) plus the same
gateway and probe set on each. Nothing in the core changes (§24).

**Accepted risk:** a total failure of Host T also stops its Prometheus and Alertmanager, so no new
alerts arrive until T recovers. Argus's own alert rules (§18.4) and scheduled checks show the silence.

Every component runs in a Docker container managed by Docker Compose. Host placement is configuration
only; no domain or application code knows which host it runs on.

### 3.2 Networks and the private cross-host path

| Network | Host | Members | Purpose |
|---|---|---|---|
| `argus-internal` | A | api, worker, scheduler, postgres | Argus state and control |
| `target-monitoring` | T | prometheus, alertmanager, exporters, gateways, host-probe | monitoring + restricted target operations |
| `app` | T | monitored workloads, network-probe, db-probe | workload traffic + target-perspective probes |
| **private cross-host path** | A↔T | host interfaces/firewalls | the only path between hosts |

The private cross-host path **MUST** satisfy all of the following:

1. Hosts communicate over a **private network** (a shared private subnet or cloud VCN). When the path
   crosses any network that is not private to the deployment, an **encrypted tunnel** (WireGuard) is
   required.
2. Every service on Host T that Host A must reach (Prometheus query API, gateways, probes) is
   **published only on the private address**, never on `0.0.0.0` and never on a public interface. For
   Docker-published ports the **bind address is the effective control**, because Docker's own rules
   are evaluated before the host's `INPUT` chain.
3. Source restrictions for published container ports live in the **`DOCKER-USER`** chain (or the
   equivalent), allowing only the peer host's private address on the required ports.
4. Every service call carries a **per-service credential** (§17.2).

- No Docker bridge spans hosts.
- `network-probe` has the minimum dual attachment it needs (receives requests from the monitoring
  side, originates probes in `app`). IP forwarding is disabled, and it exposes allowlisted verbs only,
  not a generic proxy.
- Nothing listed is exposed to the public Internet.
- **Accepted risk for a private subnet without a tunnel:** service credentials travel in plain HTTP
  inside the subnet. TLS or a tunnel becomes mandatory before any path leaves the private network.

### 3.3 Communication matrix

| From | To | Protocol | Purpose | Authentication |
|---|---|---|---|---|
| Prometheus | exporters (T) | HTTP scrape | metrics | local network |
| Prometheus | Argus `/metrics` (A) | HTTP scrape over the private path | Argus self-monitoring | private path + firewall |
| Prometheus | Alertmanager | HTTP | alert delivery | local |
| Alertmanager | Argus `POST /api/v1/alerts` | HTTP over the private path | primary trigger | bearer service token (§17.2) |
| argus-worker | Prometheus query API | HTTP over the private path | detection, verification, reconciliation | private path + source restriction |
| argus-worker (tools server child) | Prometheus query API | HTTP over the private path | model-selected metric history (named templates only) | private path + source restriction |
| argus-worker (tools server child) | docker-read-gateway | HTTP over the private path | container diagnostics | per-(host, executor) credential + exact routes |
| argus-worker (tools server child) | host-probe / network-probe / db-probe | HTTP over the private path | target-context diagnostics | per-(host, executor) credential + allowlisted verbs |
| argus-worker (write path) | action-gateway | HTTP over the private path | approved write action | credential + exact route/target + action ID; **only after that capability's write gate** |
| argus-worker | model endpoint | HTTPS egress | reasoning | provider API key |
| argus-worker | Slack/email | HTTPS/SMTP egress | notifications | provider credentials |
| argus-scheduler | argus-api (or application directly) | internal HTTP or in-process | scheduled triggers | internal service identity |
| Human | Argus API | HTTP(S) over a loopback-bound SSH tunnel or VPN | manual trigger, approval, incident view | human login ⇒ short-lived JWT (§17.3) |
| Peer agent (reserved) | Argus peer adapter | authenticated HTTP(S) over the private path | investigations, findings, evidence, holds | agent client credentials ⇒ JWT (§23) |
| worker ↔ MCP tools server | stdio pipes | MCP | read-only tool discovery/invocation | process identity (§12.6) |
| Monitored workloads | Argus API, Postgres, gateways | — | — | **forbidden** |
| Internet | any Argus or Host-T service | — | — | **forbidden** |

### 3.4 Topology diagram

```mermaid
flowchart TB
    HUMAN[Operator / Approver]
    PEER[Peer security agent]
    MODEL[Model endpoint]
    NOTIFY[Slack / email]

    subgraph T["Host T — Target + Monitoring"]
      APP["monitored workloads"]
      NODE[node-exporter]
      CADV[cAdvisor]
      AEXP[argus-exporter]
      PROM[Prometheus]
      AM[Alertmanager]
      READ[docker-read-gateway]
      ACTG[action-gateway]
      HP[host-probe]
      NP[network-probe]
      DBP[db-probe]
      NODE --> PROM
      CADV --> PROM
      AEXP --> PROM
      PROM --> AM
      NP --> APP
      DBP --> APP
      READ --> DOCKER[(Docker daemon)]
      ACTG --> DOCKER
    end

    subgraph A["Host A — Agent"]
      API[argus-api]
      WORK[argus-worker]
      MCPS["MCP tools server (stdio child, UID argus-tools)"]
      SCHED[argus-scheduler]
      PG[(Postgres)]
      API --- PG
      WORK --- PG
      SCHED --> API
      WORK -->|stdio MCP| MCPS
    end

    AM -->|token webhook / private path| API
    WORK -->|private path| PROM
    MCPS -->|private path| PROM
    MCPS -->|private path| READ
    MCPS -->|private path| HP
    MCPS -->|private path| NP
    MCPS -->|private path| DBP
    WORK -. "after write gate only" .-> ACTG
    WORK --> MODEL
    WORK --> NOTIFY
    HUMAN -->|SSH tunnel / VPN| API
    PEER -. "reserved (§23)" .-> API
```

### 3.5 Container inventory

| Container | Host | Image | Notes |
|---|---|---|---|
| `argus-api` | A | Argus image, `api` command | FastAPI/Uvicorn; exposes `/api/v1/*`, `/docs` and `/metrics` |
| `argus-worker` | A | Argus image, `worker` command | claims intake; runs graphs, resume, expiry and outbox loops; spawns the MCP tools server as a child |
| `argus-scheduler` | A | Argus image, `scheduler` command | cron-style; submits triggers only |
| `postgres` | A | PostgreSQL 16, named volume | all Argus durable state |
| `prometheus`, `alertmanager` | T | upstream images | **Argus-owned** instances with Argus alert rules; they may scrape exporters that already exist on the host, and never modify another team's monitoring |
| `node-exporter`, `cadvisor` | T | upstream images | host and container resource metrics; reused if already present |
| `argus-exporter` | T | custom | `oom_killed`, `last_exit_code` and lifecycle facts cAdvisor does not publish |
| `docker-read-gateway` | T | custom or ACL proxy | exact GET allowlist (§4.4) |
| `action-gateway` | T | custom service | exact write routes + action journal (§4.5); deployed/reachable only after a write capability is released |
| `host-probe`, `network-probe`, `db-probe` | T | custom | verb APIs, no shell (§4.6) |
| workloads | T | existing | monitored stack |

Every container **MUST** have a memory limit, and every image **MUST** exist for the hosts'
CPU architecture.

### 3.6 First deployment instance

These values are configuration (inventory, settings, `deploy/`), recorded here for reference only.

| | Host A | Host T |
|---|---|---|
| Logical name | `host-a` | `host-t` |
| Machine | VM 0.95 (see `brain/infrastructure/environment.md`) | VM 0.166 (see `brain/infrastructure/environment.md`) |
| Private address | `<host-a private IP>` (VM-local `/opt/argus-v18/hosts.env`) | `<host-t private IP>` (same file) |
| Shared subnet | `10.0.0.0/24` (same cloud VCN) | same |
| Architecture | ARM64, 1 vCPU, 5.8 GiB RAM, no swap | same |
| Cross-host path | private subnet, no tunnel (accepted risk of §3.2) | same |
| API exposure | `127.0.0.1:8000` for humans (SSH tunnel), `<host-a private IP>:8000` for the webhook from `<host-t private IP>` only | — |
| Pre-existing monitoring | — | a shared Prometheus on `:9090`, node-exporter, cAdvisor (not Argus's; left untouched) |

`MAX_ACTIVE_INVESTIGATIONS` stays at its default of 2 or lower on this hardware.

---

## 4. Monitoring and target-side components

### 4.1 Metric sources and the signal catalogue

```text
Docker/cgroups → cAdvisor ─────────┐
Host OS → node-exporter ───────────┼→ Prometheus → alert rules → Alertmanager → Argus API
Docker API → argus-exporter ───────┘      ↑
                                         ├── MetricsPort ← PrometheusMetrics adapter ← detection, verification
                                         └── metrics.* capabilities ← model-selected history (named templates)
```

- **cAdvisor:** per-container CPU, memory, network and resource usage.
- **node-exporter:** host CPU, RAM, disk, load, I/O and network.
- **argus-exporter:** lifecycle facts cAdvisor does not publish (`oom_killed`, `last_exit_code`,
  restart count and similar).
- Argus queries **only Prometheus** for metrics. It never queries an exporter directly.
- Endpoint availability comes from a blackbox-style exporter rule or a scheduled probe.

**Signal catalogue** (`config/signals.yaml`). Every metric Argus uses has a **signal name** mapped to a
PromQL template with named parameters, for example:

```yaml
container_memory_usage_bytes: 'container_memory_working_set_bytes{name="{container}"}'
container_restart_count:      'argus_container_restart_count{container="{container}"}'
host_disk_used_ratio:         '1 - node_filesystem_avail_bytes{mountpoint="{mount}"} / node_filesystem_size_bytes{mountpoint="{mount}"}'
```

The same catalogue serves three consumers: detection snapshots, post-action verification and the
`metrics.*` history capabilities. Template parameters are filled only from validated target and
inventory values; **free-form PromQL is never accepted from a model, a peer or a request body.** A new
signal is a configuration change, not an adapter change.

### 4.2 Alertmanager

Each Host T runs an **Argus-owned** Alertmanager beside the Argus-owned Prometheus. Alertmanager groups
and deduplicates alerts. It posts to Argus's webhook over the private path with a bearer token read
from a file (`http_config.authorization.credentials_file`), and it retries on non-2xx responses. Argus
returns 2xx only after durable intake (§6.2).

### 4.3 Docker API threat model

Docker API access is root-equivalent, so HTTP-method filtering alone is **not** a security boundary.
Argus **never** gets the Docker socket or a broad Docker API proxy. It reaches Docker only through two
exact-route gateways on each Host T.

### 4.4 `docker-read-gateway`

Allowed routes, and only for container names in the policy-approved read scope:

```text
GET /containers/json                                    (response filtered to in-scope containers)
GET /containers/{allowed}/json
GET /containers/{allowed}/logs
GET /containers/{allowed}/stats?stream=false
GET /containers/{allowed}/top
GET /events?since=…&until=…                              (filtered server-side to in-scope containers)
GET /system/df                                          (response reduced to per-category totals)
```

Everything else is denied: `/archive`, `/export`, `/exec`, create/start/stop/kill/restart, images,
volumes, secrets, auth and any other route. The response is 403. The capability layer surfaces it as a
refusal and audits it. Argus **MUST NOT** fall back to any other Docker access.

Container network information (`container.network`) is derived from `/containers/{allowed}/json`
(`NetworkSettings`); there is no `/networks` route.

`container.inspect` and every capability built on it **MUST** redact `Config.Env`, mount/secret fields
and other configured secret-like fields before building an `Observation`. Raw inspect JSON never
reaches the model.

### 4.5 `action-gateway`

The action gateway carries out **released write capabilities only**. It is generic over actions and
exact per action:

- Each released write capability has **one exact route** and an exact target allowlist, for example
  `POST /containers/{name}/restart` for `container.restart`. Routes and target lists change only
  together with the policy data file, in review.
- It denies every other Docker operation and every action on Prometheus, Alertmanager, the gateways or
  the probes.
- Every request **MUST** carry `X-Argus-Action-Id`; a request without it is rejected.
- **Action journal:** before and after calling Docker, the gateway appends
  `(action_id, capability, target, target_identity, received_at, docker_status)` to a local journal. A
  second request with an already-accepted `action_id` is refused.
- `GET /actions/{action_id}` (same ACL, read-only) reports whether that action was received and what
  Docker returned. Reconciliation uses it (§14.5).
- **Write gate:** until a capability's release criteria (§22.2) pass, its route does not exist in the
  gateway configuration. While no write capability is released, the gateway is not deployed, the
  firewall rule from Host A is closed, and the worker holds no action credential.

*Implementation choice:* the read gateway may be an ACL-configured reverse proxy (HAProxy/nginx) or a
small custom service. The action gateway needs custom logic for its journal. A write action that
Docker cannot express (a host service, a configuration file) needs its own gateway design and review
before release.

### 4.6 Target-side probe services

Host, network and database diagnostics **MUST** run on the target host, so that observations describe
the target and not Host A. A Host-A-local substitute is never allowed.

| Service | Verbs | Privileges |
|---|---|---|
| `host-probe` | `cpu`, `memory`, `disk_usage(mount)`, `load`, `io`, `uptime`, `top_processes(by, n)`, `process_details(pid)`, `directory_sizes(path)`, `socket_summary`, `journal(unit, since, lines)`, `kernel_oom_records(since)`, `read_file(path, lines)` | read-only host mounts it needs (`/proc`, `/sys`, the journal directory, allowlisted paths); no Docker socket |
| `network-probe` | `resolve_dns(name)`, `tcp_connect(host, port, timeout)`, `http_probe(url, timeout)`, `connectivity(from_network, to_target)`, `listening_ports` | no filesystem or Docker socket access; runs in the `app` network context |
| `db-probe` | `database_health(target)`: connections by state and client, locks, long transactions, pool saturation | a read-only monitoring database role; never reads business rows |

- Every verb is allowlisted, typed and bounded. No probe offers shell execution.
- Paths (`directory_sizes`, `read_file`), units (`journal`), endpoints and ports accepted by a probe
  come from the inventory and the inspection policy; the probe re-checks them against its own local
  allowlist.
- *Implementation choice:* the exact route and JSON shapes of the probe APIs, as long as the Argus
  capability returns the standard `Observation` (§12.3).

### 4.7 Inspection policy (files, logs, processes)

Argus does not get unrestricted filesystem access because it can inspect a target. A per-target
**inspection policy** in the policy data file (§13.1) states what may be read:

```yaml
inspection:
  host-t/container:shop-api:
    logs:      {max_lines: 500, redact_secrets: true}
    processes: true
    files:     [/app/diagnostics/, /var/log/myapp/]
  deny:        [environment_variables, /run/secrets/, /root/, "*.key", "*.pem", ".env"]
  arbitrary_exec: false
```

- Files inside a container are readable **only** through paths the deployment mounts read-only into
  `host-probe` (for example a container's log volume). Docker `/archive` and `/exec` stay forbidden.
- Deny patterns win over allow entries. `arbitrary_exec` is always `false`.
- Every file or log read is redacted and bounded like any other observation.

---

## 5. Domain model

All types are immutable value objects unless stated otherwise. Field lists are the required minimum;
additional fields are allowed. **Growth rule:** vocabularies that grow with Argus's reach (target
kinds, incident classes, capabilities, strategies, audit event names) are *registered values*
validated at startup, not closed `Literal` types. Only vocabularies that encode safety states
(approval states, action states, outcomes, trigger kinds, principal kinds) are closed.

### 5.1 Identity and targets

```python
IncidentId = NewType("IncidentId", str)      # ULID; also the LangGraph thread_id

class TargetRef(BaseModel):                  # canonical target identity
    host: str                                # logical host name from the inventory, e.g. "host-t"; never an IP
    kind: str                                # registered target kind: container | host | network_endpoint
                                             # | database | service | volume | …
    name: str                                # e.g. "shop-api"
    # text form: "host-t/container:shop-api"
```

- The target kind registry lives in `domain/target.py`. A kind that is not registered is rejected.
- `host` is part of every key that contains a target: proposal digests, idempotency keys, locks,
  correlation and audit.

### 5.2 Principals, triggers and alerts

```python
class Principal(BaseModel):                  # derived server-side from authentication; never from a body
    id: str                                  # "alice", "alertmanager@host-t", "security-agent"
    kind: Literal["human", "service", "agent"]
    role: Literal["viewer", "operator", "approver", "service", "peer_agent"]
    scopes: frozenset[str]                   # target-scope names from the policy data file

class TriggerKind(StrEnum):
    alert = "alert"; manual = "manual"; scheduled = "scheduled"; system = "system"; peer = "peer"

class InvestigationRequest(BaseModel):
    target: TargetRef
    reason: str
    trigger_kind: TriggerKind                # manual | scheduled | system | peer
    request_kind: Literal["check", "report"] # check: "is it healthy?"; report: "there is a problem" (§9)
    trigger_id: str                          # idempotency identity, see §6.6
    requested_at: datetime
    principal: Principal | None              # authenticated human/service/agent caller
    correlation_id: str                      # propagated across agents; joins logs, audit and peer records
    origin_chain: list[str] = []             # agents this request already passed through (loop protection, §23)
    reported_evidence: str | None = None     # peer finding / human description; untrusted, redacted, stored as evidence
    schedule_id: str | None = None
    scheduled_for: datetime | None = None

class AlertNotification(BaseModel):          # vendor-neutral translation of an Alertmanager alert
    fingerprint: str
    status: Literal["firing", "resolved"]
    starts_at: datetime
    ends_at: datetime | None
    labels: dict[str, str]
    annotations: dict[str, str]
    target: TargetRef | None                 # resolved from labels + inventory

class TriggerOccurrence(BaseModel):          # every trigger that touched an incident
    incident_id: IncidentId | None
    kind: TriggerKind
    trigger_id: str
    principal: str | None
    scheduled_for: datetime | None
    disposition: Literal["started", "attached", "coalesced", "stale_skipped", "duplicate", "refused"]

class AlertOccurrence(BaseModel):            # per-fingerprint status within an incident
    fingerprint: str
    status: Literal["firing", "resolved"]
    starts_at: datetime
    resolved_at: datetime | None
```

### 5.3 Incident

```python
class IncidentStatus(StrEnum): open = "open"; closed = "closed"; escalated = "escalated"

class IncidentOutcome(StrEnum):
    no_incident = "no_incident"                     # detection healthy; no model call
    undiagnosable = "undiagnosable"                 # stale/unavailable metrics
    unsupported_escalated = "unsupported_escalated" # reported, but no registered class matches; evidence pack only
    diagnosed = "diagnosed"                         # diagnosis concluded; no action taken by Argus
    recovered_verified = "recovered_verified"       # Argus action confirmed + fresh verification
    resolved_externally = "resolved_externally"     # recovered without a verified Argus action
    action_failed = "action_failed"
    indeterminate_escalated = "indeterminate_escalated"
    denied = "denied"
    expired = "expired"
    no_action_escalated = "no_action_escalated"     # diagnosis/escalation without action

class Incident(BaseModel):
    id: IncidentId
    target: TargetRef                               # the target the trigger named
    incident_class: str | None                      # registered class; None when unsupported
    strategy: str | None                            # diagnostic strategy that ran
    status: IncidentStatus
    outcome: IncidentOutcome | None
    affected_targets: list[TargetRef]               # targets showing symptoms
    root_cause_target: TargetRef | None             # set by a concluded diagnosis
    related_incident_ids: list[IncidentId]          # linked, never merged automatically (§6.4)
    evidence_version: int                           # +1 on every attached evidence/trigger/alert
    opened_at: datetime
    last_evidence_at: datetime
    closed_at: datetime | None
```

### 5.4 Evidence

```python
class MetricSnapshot(BaseModel):
    target: TargetRef
    observed_at: datetime                   # timestamp of the newest sample used
    values: dict[str, float | int | bool]   # keyed by signal name from the signal catalogue (§4.1)

class Passage(BaseModel):                   # runbook passage
    runbook_id: str                         # from the runbook's metadata `id`, never the file name
    runbook_version: str; runbook_status: str   # e.g. "1.0.0", "draft"
    section: str; text: str; score: float

class EvidenceRecord(BaseModel):            # insert-only; one per observation, snapshot or reported finding
    evidence_id: str                        # equals Observation.observation_id for observations
    incident_id: IncidentId
    kind: Literal["observation", "metric_snapshot", "alert", "peer_finding", "reported_symptom"]
    capability: str | None
    target: TargetRef | None
    host: str | None
    executor: str | None
    caller: str                             # principal id, "model", "strategy:<name>" or "system"
    observed_at: datetime
    status: str
    values: dict[str, JsonValue]            # redacted, bounded
    model_text: str                         # one-line rendering
    truncated: bool; redactions: int
    sha256: str                             # over the canonical JSON of the fields above

class EvidenceRef(BaseModel):               # points at a stored record or a recalled item
    kind: Literal["evidence", "passage", "prior_incident"]
    id: str
    sha256: str | None = None               # required for kind="evidence"
```

- Every observation, the detection snapshot, attached alerts and reported findings are stored **once**
  as `EvidenceRecord` (§16.1). Graph state, context, proposals, views and peers refer to them by
  `EvidenceRef`.
- A reference with a hash binds to exact content; a record is never updated.

`Observation` and `CapabilitySpec` are defined in §12.3.

### 5.5 Decisions

```python
class ReadCall(BaseModel):
    name: str; arguments: dict

class UseReadTools(BaseModel):
    kind: Literal["use_read_tools"]
    calls: list[ReadCall]                   # 1 ≤ len ≤ MAX_READS_PER_STEP (default 1)

class ProposeRemediation(BaseModel):
    kind: Literal["propose_remediation"]
    capability: str                         # constrained to a policy-generated enum per request
    target: TargetRef                       # constrained to policy-allowed targets
    arguments: dict                         # validated against that capability's schema
    rationale: str                          # ≤ 500 chars
    evidence_refs: list[EvidenceRef]        # must exist for this incident

class Conclude(BaseModel):
    kind: Literal["conclude"]; diagnosis: str; evidence_refs: list[EvidenceRef]
    confidence: Literal["low", "medium", "high"]
    root_cause_target: TargetRef | None = None

class Escalate(BaseModel):
    kind: Literal["escalate"]; reason: str; evidence_refs: list[EvidenceRef]

AgentDecision = Annotated[UseReadTools | ProposeRemediation | Conclude | Escalate,
                          Field(discriminator="kind")]

class InvalidDecision(BaseModel):
    reason: Literal["fabricated_tool", "malformed", "multiple_calls", "no_decision",
                    "provider_length", "provider_content_filter", "provider_error"]
    detail: str

class ApprovalDecision(BaseModel):
    approval_id: str; decision: Literal["approved", "denied", "expired", "cancelled"]
```

Decisions are produced by **every** strategy, whether a model or deterministic code chose them. The
skeleton treats them identically.

### 5.6 Proposals, approvals, holds and actions

```python
class ActionProposal(BaseModel):            # insert-only
    proposal_id: str
    incident_id: IncidentId
    capability: str                         # e.g. "container.restart"
    target: TargetRef
    target_identity: dict                   # from the capability's identity(target) at proposal time (§14.8)
    arguments: dict
    evidence_refs: list[EvidenceRef]        # with hashes
    evidence_version: int
    policy_version: str                     # SHA-256 of the policy data file
    inventory_version: str                  # SHA-256 of the inventory data file
    created_at: datetime
    expires_at: datetime
    digest: str                             # SHA-256 over canonical JSON of the fields above

class ApprovalState(StrEnum): pending="pending"; approved="approved"; denied="denied"; expired="expired"; cancelled="cancelled"

class Approval(BaseModel):
    approval_id: str; proposal_id: str; proposal_digest: str
    state: ApprovalState; approver_scope: str
    actor: str | None                       # derived server-side, never from request body; always a human
    requested_at: datetime; expires_at: datetime; answered_at: datetime | None

class TargetHold(BaseModel):                # forbids writes on a target (§13.5)
    hold_id: str; target: TargetRef; reason: str
    placed_by: str; placed_at: datetime; expires_at: datetime | None
    released_by: str | None; released_at: datetime | None

class ResumeIntent(BaseModel):
    approval_id: str; incident_id: IncidentId; decision: ApprovalDecision
    state: Literal["pending", "done", "failed"]; attempts: int; last_outcome: str | None

class ActionState(StrEnum):
    unstarted="unstarted"; attempting="attempting"; confirmed="confirmed"; failed="failed"; indeterminate="indeterminate"

class ActionRecord(BaseModel):
    action_id: str; proposal_id: str; approval_id: str; state: ActionState
    attempted_at: datetime | None; result_at: datetime | None; evidence: dict
```

### 5.7 Audit

```python
class AuditCategory(StrEnum):
    tool = "tool"; decision = "decision"; approval = "approval"; action = "action"
    access = "access"; security = "security"; peer = "peer"; hold = "hold"; incident = "incident"

class AuditRecord(BaseModel):               # append-only
    audit_id: str
    incident_id: IncidentId | None
    correlation_id: str | None
    at: datetime
    category: AuditCategory                 # closed
    event: str                              # registered name within the category
    capability: str | None
    arguments: dict | None                  # redacted
    policy_rule: str | None                 # which rule allowed/refused
    policy_version: str | None
    actor: str | None                       # principal id, "model", "strategy:<name>" or "system"
    evidence_id: str | None                 # the stored evidence this record concerns
    detail: dict                            # redacted
```

Core registered events include: `tool.requested`, `tool.refused`, `tool.completed`, `tool.failed`,
`decision.invalid`, `decision.strategy_selected`, `incident.unsupported`, `incident.evidence_pack`,
`approval.proposal_created`, `approval.requested`, `approval.answered`, `approval.noop`,
`approval.cancelled`, `action.attempting`, `action.confirmed`, `action.failed`, `action.indeterminate`,
`action.verification_result`, `security.event`, `access.incident_read_denied`, `access.budget_exhausted`,
`peer.request_received`, `peer.request_refused`, `hold.placed`, `hold.released`.

**Requirement:** every capability request (from any caller), refusal and result, every policy decision,
every proposal, every approval answer (including no-ops), every action state transition, every hold
change, every peer request and every security event produces an audit record.

### 5.8 Inventory, incident classes and strategies

These are the registered descriptors that let Argus grow without core changes.

```python
class HostInfo(BaseModel):
    name: str                               # "host-t"
    executors: dict[str, str]               # executor name → endpoint URL (no credentials)

class TargetInfo(BaseModel):
    ref: TargetRef
    depends_on: list[TargetRef]
    scope: str                              # target-scope name used by policy and approvers
    http_endpoints: list[str]               # allowlisted for network.http_probe
    tcp_ports: list[int]                    # allowlisted for network.tcp_connect
    mounts: list[str]                       # allowlisted for host.disk_usage

class IncidentClassSpec(BaseModel):
    name: str                               # "disk_pressure"
    family: str                             # "saturation"
    target_kinds: set[str]
    detector: Callable[[MetricSnapshot], DetectorResult]   # pure
    required_signals: set[str]              # from the signal catalogue
    runbook_ids: list[str]                  # primary first, e.g. ["RB-001", "RB-008"]
    branch_runbook_ids: list[str]           # retrieved when the investigation points to that cause
    strategy: str                           # registered strategy name
    tool_tags: set[str]                     # which capabilities to offer (plus all Level 1)
    budgets: ClassBudgets                   # steps, tokens; capped by the global ceilings
    verification_signals: set[str]
    owner: Literal["argus", "peer"] = "argus"   # "peer": routed to a peer agent (§15.2)
```

- The inventory is read through `InventoryPort` (§8.1). **Incident scope** is the incident's target
  plus its direct dependencies and dependents in the inventory; reads outside it are refused by policy.
- The class registry, the capability registry and the strategy registry are validated together at
  startup: every signal, runbook, strategy, tool tag and executor they name must exist, or Argus
  refuses to start.

---

## 6. Application layer

### 6.1 Use cases

| Use case | Contract | Driven by |
|---|---|---|
| `HandleAlertNotification` | `(AlertNotification, service_principal) -> IntakeResult` | Alertmanager HTTP adapter; `ReconcileFiringAlerts` |
| `RunInvestigation` | `(InvestigationRequest) -> IntakeResult` (contains `IncidentId` once known) | manual HTTP, CLI, scheduler, peer-agent adapter |
| `InvokeCapability` | `(CapabilityRequest) -> Observation` — the single guarded entry point (§12.4) | the `act` node, combined capabilities, the evidence pack, the peer-agent adapter (`retrieve_evidence` reads stored evidence only) |
| `AnswerApprovalRequest` | `(IncidentId, approval_id, proposal_digest, answer, authenticated_principal) -> ApprovalResult` | approval HTTP, CLI; **human principals only** |
| `PlaceTargetHold` / `ReleaseTargetHold` | `(TargetRef, reason, expires_at, authenticated_principal) -> TargetHold` | HTTP, CLI, peer-agent adapter |
| `GetIncident` | `(IncidentId, authenticated_principal) -> IncidentView` | HTTP, CLI, peer-agent adapter |
| `ListIncidents` / `ListPendingApprovals` | `(filters, authenticated_principal) -> list[view]` | HTTP, CLI |
| `ReconcileFiringAlerts` | `() -> ReconcileResult` | scheduler only (feature flag) |
| `ResumeAnsweredApprovals` | `() -> int` (intents processed) | worker loop only |
| `DeliverNotifications` | `() -> int` (outbox items delivered) | worker loop only |

All triggers converge **before** detection, so no trigger path can bypass detection, policy, audit or
HITL:

```text
A. Alertmanager webhook ─→ HandleAlertNotification ─┐
B. Human HTTP / CLI ────→ RunInvestigation ─────────┤
C. Scheduler tick ──────→ RunInvestigation ─────────┼→ durable intake → worker claim → InvestigationRunner.start
E. Peer agent ──────────→ RunInvestigation (peer) ──┘
D. Scheduler reconcile ─→ ReconcileFiringAlerts → HandleAlertNotification semantics
```

### 6.2 Intake

- An HTTP handler authenticates, validates, translates and **durably persists** the trigger into the
  Postgres intake table, and only then returns `202 Accepted` (for alerts, a 2xx acceptable to
  Alertmanager). It never waits for the investigation.
- A request whose principal lacks scope for the target, or whose `origin_chain` already contains
  Argus or exceeds `MAX_ORIGIN_CHAIN`, is recorded as a `refused` occurrence and audited.
- Reported evidence (a peer finding or a human description) is redacted and stored as an
  `EvidenceRecord` at intake. It is data, never instructions.
- Duplicate triggers, identified per §6.6, are recorded as `duplicate` occurrences and do not create
  new work.
- The worker claims intake rows transactionally (e.g. `SELECT … FOR UPDATE SKIP LOCKED`) so that more
  than one worker can run safely. A crashed worker's claim is recovered after a lease timeout.

### 6.3 `InvestigationRunner` (application-owned orchestration protocol)

```python
class ResumeOutcome(StrEnum):
    resumed = "resumed"; not_yet_waiting = "not_yet_waiting"
    already_past = "already_past"; incident_closed = "incident_closed"

class InvestigationRunner(Protocol):
    def start(self, incident_id: IncidentId) -> None: ...
    def resume(self, incident_id: IncidentId, decision: ApprovalDecision) -> ResumeOutcome: ...
```

- `start` runs, or continues from its last checkpoint, the graph for `thread_id = incident_id`.
- `resume` **MUST** be idempotent. It resumes only if the checkpoint is paused at `await_approval` for
  the same `approval_id`; otherwise it returns the reason and does nothing.
- Only `ResumeAnsweredApprovals` calls `resume`. HTTP handlers never do.
- `orchestration/runner_langgraph.py` implements it with LangGraph invoke/resume semantics.

### 6.4 Correlation (`application/correlation.py`)

When an alert, or a manual/scheduled/peer request whose detection finds an incident, arrives, it is
matched in this order:

1. an open incident containing this fingerprint → attach;
2. otherwise, an open incident with the same target and incident class **whose `last_evidence_at` is
   within `CORRELATION_WINDOW`** *(default 30 min)* **and which passes the compatibility test** →
   attach;
3. otherwise, create a new incident.

**Compatibility test:** re-run the class's detector on a fresh snapshot for the new alert's target.
The alert is compatible only if the detector returns the same class for the same target, *and* its
labels do not name a different container or dependency than the incident's canonical target.
Independent failures are therefore never merged.

**Related incidents.** When a new incident's target is a direct dependency or dependent (per the
inventory) of an open incident's target, both incidents record each other in `related_incident_ids`.
They are **linked, never merged automatically**; the context of each includes a one-line summary of
the other. Merging is Open Decision OD-13.

**Evidence version:** every attach increments `Incident.evidence_version` and updates
`last_evidence_at`.

**Resolution:** each `AlertOccurrence` has its own status, and a `resolved` notification marks only
that fingerprint resolved. An incident may close from alert resolution **only when all attached
fingerprints are resolved and no write or verification is in flight**. It then closes with
`resolved_externally`, unless a confirmed Argus action followed by successful fresh verification
already set `recovered_verified`.

### 6.5 Scheduling policy (`application/scheduling_policy.py`)

| Rule | Behaviour |
|---|---|
| **Skip-if-active** | When a scheduled request is claimed while its target already has an open incident or an active run (including one paused for approval), it is recorded as a `coalesced` occurrence on that incident. No new run starts and no second approval is created. |
| **Maximum queued age** | A scheduled request not claimed within `SCHEDULE_MAX_QUEUED_AGE` *(default: one cadence interval)* is recorded as `stale_skipped`. Manual, alert and peer requests are exempt. |
| **Concurrency ceiling** | At most `MAX_ACTIVE_INVESTIGATIONS` *(default 2)* model-using runs system-wide, and at most one active run per target. Excess work waits in intake. |
| **Daily cost ceiling** | `MAX_MODEL_COST_PER_DAY` across all incidents. When it is exhausted, detection still runs, but a detected incident escalates with deterministic evidence and no model call. |
| **Per-principal quota** | `MAX_MODEL_COST_PER_PRINCIPAL_PER_DAY` and a request-rate limit per service or agent principal, so that no single caller (in particular a peer agent) can exhaust the shared budget. |
| **Cadence floor** | Each schedule's interval MUST be ≥ 2 × the measured p95 investigation duration for that target (approval wait excluded). The scheduler refuses, and logs, configurations below the floor. |

### 6.6 Trigger identity and idempotency

| Trigger | Identity |
|---|---|
| Alert | `fingerprint + startsAt` |
| Manual | caller-supplied idempotency key if present, otherwise a unique request ID |
| Scheduled | `schedule_id + scheduled_for` |
| Peer | `principal id + the peer's request ID` |
| Approval | `approval_id`, bound to `proposal_id + proposal_digest` |
| Write action | `action_id` (one per approved proposal, never reused) |

Identity belongs to the incident, not the target. The same target can have many incidents over time.

### 6.7 Read authorization (`GetIncident`, `ListIncidents`, `ListPendingApprovals`)

The caller must be authenticated. Authorization depends on role and target scope, and the view is
redacted (§10.6) for that role:

| Role | May read | View contents |
|---|---|---|
| `viewer` | incidents for in-scope targets | status, incident class, timestamps, outcome |
| `operator` | incidents for in-scope targets | + redacted evidence excerpts, diagnosis, audit summary |
| `approver` | incidents for in-scope targets, and pending approvals within the approver's scope | + the full immutable proposal to decide, with its `approval_id` and `proposal_digest` |
| `service` | incidents it created | status only |
| `peer_agent` | incidents it created, and incidents for targets in its scopes | status, class, diagnosis, evidence records scoped to its targets |

An unauthorized read returns **404** (not 403) and is audited as `access.incident_read_denied`.

---

## 7. Inbound adapters

### 7.1 HTTP API (`adapters/inbound/http`, FastAPI)

| Method & path | Use case | Caller auth | Notes |
|---|---|---|---|
| `POST /api/v1/auth/token` | — (authentication, §17.3) | username + password (humans) or client credentials (agents) | returns a short-lived JWT |
| `POST /api/v1/alerts` | `HandleAlertNotification` | Alertmanager bearer token | Alertmanager webhook payload; returns 2xx only after durable intake |
| `POST /api/v1/investigations` | `RunInvestigation` (`manual`) | JWT: operator or approver | body: `target`, `reason`, optional `idempotency_key`; no `force_reasoning` flag exists |
| `GET /api/v1/incidents` | `ListIncidents` | JWT | filters: status, class, target, since |
| `GET /api/v1/incidents/{id}` | `GetIncident` | JWT | role-redacted view |
| `GET /api/v1/incidents/{id}/events` | run events of an incident | JWT | the node timeline (CLI and UIs) |
| `GET /api/v1/evidence/{id}` | one evidence record | JWT: operator or approver | |
| `GET /api/v1/escalations` | escalations waiting for a human | JWT | |
| `GET /api/v1/me` | — (who am I) | JWT (read or full) | `user`, `role`, `access` and the `actions` this token may use (e.g. `view_incidents`, `view_timeline`, `view_evidence`); a UI shows a control only when its action is listed (ACR-0001) |
| `GET /api/v1/approvals?state=pending` | `ListPendingApprovals` | JWT: approver | shows each proposal with `approval_id` and `proposal_digest` |
| `POST /api/v1/incidents/{id}/approve` | `AnswerApprovalRequest` | JWT: human approver (later also a signed single-use link) | body: `approval_id`, `proposal_digest` |
| `POST /api/v1/incidents/{id}/deny` | `AnswerApprovalRequest` | same | same |
| `POST /api/v1/holds`, `DELETE /api/v1/holds/{id}` | `PlaceTargetHold` / `ReleaseTargetHold` | JWT: operator or approver | body: `target`, `reason`, optional `expires_at` |
| `GET /healthz`, `GET /readyz` | — | none | liveness; readiness checks Postgres and settings |
| `GET /docs`, `GET /openapi.json` | — | loopback only | Swagger UI (the approval console in this release); served only on the loopback listener |
| `GET /metrics` | — | private path + firewall | Prometheus exposition |

*Implementation choice:* response JSON shapes, and whether the scheduler calls the API over internal
HTTP or the application in-process.

**Request rules:**
- The request body can never set `actor`; the server derives it from the authenticated identity.
- Payload schemas are validated with Pydantic; unknown fields are rejected.
- Answering an approval requires a principal of kind `human`. Service and agent principals are
  refused and audited, whatever their role claims.
- The alert adapter translates Alertmanager's JSON into `AlertNotification` and counts
  truncated alerts (`truncatedAlerts > 0`) and unsupported ones.
- **Read-only tokens** (§17.3) are refused with 403 on every route that is not a `GET`, before any use case runs.
- **Browser clients:** cross-origin requests are refused unless their origin is listed in `ARGUS_UI_ORIGINS`
  (empty by default: no CORS headers at all). In production a UI container proxies the API on the same origin,
  so the list stays empty there (ACR-0001).
- **Listeners:** humans and Swagger use a loopback listener reached over an SSH tunnel or VPN. The
  Alertmanager webhook and `/metrics` use a listener on the private address, source-restricted to the
  monitoring host. The peer adapter (§23) gets its own listener.

### 7.2 CLI (`adapters/inbound/cli`)

- `argus login` → obtains a JWT with the same credentials as the API; the other commands use it.
- `argus run --target <host/kind:name> --reason <text> [--idempotency-key K]` → `RunInvestigation(manual)`.
- `argus approve|deny --incident <id> --approval <id> --digest <d>` → `AnswerApprovalRequest`.
- `argus incident <id>`, `argus incidents`, `argus approvals` → read use cases.
- `argus hold place|release …` → hold use cases.
- `argus user add|disable|reset --role … --scopes …` → user administration; available only from a
  shell on Host A (§17.3).
- `argus run --simulate-alert <fixture.json>` → only in local development; feeds a captured
  Alertmanager payload through `HandleAlertNotification`.

### 7.3 Scheduler (`infrastructure/scheduler.py`, container `argus-scheduler`)

Configuration is data (`deploy/scheduler/schedules.yaml`):

```yaml
schedules:
  - id: lab-victim-health
    cron: "*/15 * * * *"          # must satisfy the cadence floor (§6.5)
    target: "host-t/container:lab-victim"
    reason: "scheduled health investigation"
reconcile_firing_alerts:
  enabled: false
  cron: "*/5 * * * *"
```

On each tick the scheduler submits `RunInvestigation(trigger_kind="scheduled", schedule_id,
scheduled_for)`. It never calls a detector, the model or the graph. A healthy scheduled run ends after
detection with no LLM call.

`ReconcileFiringAlerts` queries each Argus-owned Prometheus's current `ALERTS` through
`MetricsPort.firing_alerts()` and replays firing alerts that are missing from Argus through
`HandleAlertNotification`. It covers alerts missed during an Argus outage.

### 7.4 Peer-agent adapter (`adapters/inbound/agent`, reserved)

Specified in §23. It is a separate listener with its own authentication, and it maps coarse verbs to
the use cases above. It never exposes graph nodes, the database, executors or policy.

---

## 8. Outbound ports and adapters

### 8.1 The seven deterministic ports (`argus/ports`)

| Port | Contract | Production adapter | Test adapter |
|---|---|---|---|
| `MetricsPort` | `snapshot(target, signals: set[str]) -> MetricSnapshot`; `range(target, signal, window, step) -> Series`; `firing_alerts(host) -> list[AlertNotification]`; raises `StaleMetrics` / `MetricsUnavailable` | `metrics_prometheus.py` (HTTP PromQL over the signal catalogue, §4.1) | `metrics_fake.py` |
| `LLMPort` | `decide(context: ModelContext, tools: list[ModelToolDefinition]) -> ModelReply` | `llm_openai.py` (OpenAI-dialect chat/tool-calling API) | `llm_mock.py` |
| `KnowledgePort` | `search(query: str, k: int) -> list[Passage]` | `knowledge_tfidf.py` over `argus/runbooks/*.md` | `knowledge_fake.py` |
| `IncidentMemoryPort` | incident, trigger, alert-occurrence, proposal, approval, hold, resume-intent, outbox, action and outcome persistence; evidence: `append_evidence(EvidenceRecord)`, `get_evidence(ids)`, `list_evidence(incident_id, filters)`; `similar_incidents(target, incident_class, k)` | `memory_postgres.py` | `memory_sqlite.py`, `memory_fake.py` |
| `AuditSinkPort` | `append(AuditRecord) -> None`; durable before return; raises on failure | `audit_postgres.py` (+ optional `audit_jsonl.py` copy) | `audit_recording.py` |
| `NotificationPort` | `notify(Notification, key) -> DeliveryResult`; adapters declare `dedupes_by_key: bool` | `notify_slack.py`, `notify_email.py`, `notify_recording.py` (this release) | `notify_recording.py` |
| `InventoryPort` | `hosts() -> list[HostInfo]`; `target(ref) -> TargetInfo | None`; `targets(host) -> list[TargetInfo]`; `neighbours(ref) -> list[TargetRef]`; `version() -> str` (SHA-256) | `inventory_yaml.py` over `config/inventory.yaml` | `inventory_fake.py` |

Provider-neutral model types live in `ports/llm.py`:

```python
class ModelToolDefinition(BaseModel):
    name: str; description: str; parameters_schema: dict       # JSON Schema

class ModelToolCall(BaseModel):
    name: str; arguments_json: str                             # raw, unvalidated

class Usage(BaseModel):
    input_tokens: int; output_tokens: int; cost_units: float

class ModelReply(BaseModel):
    text: str | None
    tool_calls: list[ModelToolCall]
    finish_reason: Literal["stop", "tool_calls", "length", "content_filter", "error"]
    usage: Usage
```

**Rules:**
- No MCP SDK types and no provider SDK types cross a port.
- `LLMPort` adapters retry transient provider errors a bounded number of times, then raise. Every
  call reports `usage`, including failed calls where the provider returns it. Provider request
  parameters (temperature, response format, timeout) are settings; a parameter the configured model
  rejects is omitted by configuration, never by code branches.
- `AuditSinkPort` failure **MUST** stop the side effect it precedes.
- `NotificationPort` is called only from `DeliverNotifications`. Delivery is **at least once**; Argus
  never claims exactly-once delivery. A peer agent may be a notification channel (§23).
- `InventoryPort` is read-only. Discovery-based inventories are future adapters behind the same port.

### 8.2 Boundary decisions

| Concern | Mechanism | Reason |
|---|---|---|
| Alertmanager → Argus | inbound HTTP adapter | deterministic notification |
| Manual / scheduled / peer trigger | inbound HTTP/CLI/scheduler/peer adapter | same use case |
| Metrics for detection and verification | `MetricsPort` over HTTP (never MCP, never model-selected) | deterministic dependency |
| Metric history chosen during an investigation | `metrics.*` capabilities over named signal templates | evidence chosen by the strategy; bounded; no free-form PromQL |
| Logs, inspect, host/network/database probes | capabilities | evidence chosen by the strategy |
| Runbook and prior-incident lookup chosen during an investigation | in-worker capabilities over `KnowledgePort` / `IncidentMemoryPort` | same guarded path as every capability |
| Model | `LLMPort` | provider portability, trust boundary, token accounting |
| Runbooks at recall | `KnowledgePort` | retriever portability |
| Hosts, targets, dependencies, endpoints | `InventoryPort` | one source for scope, validation and routing |
| Incident/approval/action/evidence state | `IncidentMemoryPort` | durable lifecycle |
| Graph start/resume | `InvestigationRunner` | keeps the application framework-free |
| Remediation | write capability under policy + human approval (never a generic port, never MCP) | authorization cannot be hidden |
| Audit | `AuditSinkPort` + mandatory call sites | backend swappable; semantics not optional |
| Tracing/telemetry | `observability/` infrastructure | optional; never an application port |

```text
our code decides     → port → adapter → technology/protocol
a strategy decides   → decision → validation → InvokeCapability (budget, audit, policy) → provider → executor
outside triggers     → driving adapter → application use case
```

---

## 9. Deterministic detection and classification

- The `detect` node selects the registered classes whose `target_kinds` include the target's kind,
  requests the union of their `required_signals` through `MetricsPort.snapshot(target, signals)`, and
  runs each applicable detector. Each detector is a pure function `(MetricSnapshot) -> DetectorResult`
  (findings, or healthy).
- If the newest sample is older than `METRICS_MAX_STALENESS`, the adapter raises `StaleMetrics`.
- If several classes match, the first in the registry's priority order becomes the incident class; the
  others are recorded as findings in the incident header.
- The snapshot is stored as an `EvidenceRecord` of kind `metric_snapshot`.
- Detectors never read the clock. Freshness is judged by the adapter or the node using an injected
  clock.

**Outcomes when no class matches:**

| Situation | Outcome | What runs |
|---|---|---|
| Stale or unavailable metrics | `undiagnosable`; escalate | evidence pack (§10.7), no model |
| Healthy, and the trigger is a `check` (scheduled, or a manual/peer request of kind `check`) | `no_incident`; closed; no escalation | nothing further |
| No class matches, and the trigger **reports a problem** (a firing alert, or a manual/peer request of kind `report`) | `unsupported_escalated`; escalate to the routing target (§15.2) | evidence pack (§10.7), no model; **no diagnosis is claimed** |
| A class matches | investigation with the class's strategy | §10 |

A class whose `owner` is `peer` is routed to that peer agent (§23) instead of being investigated by
Argus.

---

## 10. Orchestration: the safety skeleton and diagnostic strategies

### 10.1 Graph (the fixed skeleton)

The graph is the **fixed safety skeleton**. It never changes when a class, capability or strategy is
added. The only variable part is *which strategy* the `investigate` node consults.

```text
detect ─▶ recall ─▶ investigate ─▶ act ──(UseReadTools)─────────────────────────────▶ investigate
   │                     │          ├─(Conclude / Escalate / budget / invalid-limit)─▶ record
   │                     │          └─(ProposeRemediation)─▶ propose_action ─▶ request_approval ─▶ await_approval
   │                     │                                                                          │
   ▼                     │                           precheck_action ◀───────────── approved ───────┤
 evidence_pack ─▶ record │                               │ ok            denied/expired/cancelled ──▶ record
 (undiagnosable /        │                               ▼
  unsupported)           │                          execute_write ─▶ verify ─▶ record
 record (no_incident)
```

| Node | Responsibility | Side effects |
|---|---|---|
| `detect` | classify (§9); open or correlate the incident; store the snapshot as evidence; select the class's strategy | DB (incident, evidence) |
| `evidence_pack` | run the fixed evidence pack (§10.7) through `InvokeCapability` | tool calls, audit, evidence |
| `recall` | `IncidentMemoryPort.similar_incidents` (top-k) + `KnowledgePort.search` (top-k) | none |
| `investigate` | refresh the incident from the DB; check budgets; build the `InvestigationView`; ask the class's strategy for the next decision | model call if the strategy uses one; usage recorded |
| `act` | for each read call of the decision: `InvokeCapability` (§12.4); append the `ObservationRef`s to state | tool calls, audit, evidence |
| `propose_action` | check the write gate, holds and policy; persist the immutable `ActionProposal` | DB insert |
| `request_approval` | insert `Approval(pending)` + notification outbox row in **one transaction** | DB only (no notifier call) |
| `await_approval` | read the approval; if already terminal, consume it; else `interrupt()` | none before pausing |
| `precheck_action` | re-verify the proposal and current state (§14.4) | DB (cancel on mismatch) |
| `execute_write` | action ledger + dispatch through `local_write.py` (§14.5) | write; DB; audit |
| `verify` | poll `MetricsPort` until `observed_at > action_completed_at`, then check the verification signals and detector (§15.1) | none |
| `record` | set outcome/status; write the episodic summary; escalation notification to the routing target | DB; outbox |

**Graph state** (`orchestration/state.py`) holds only Argus-owned, serializable values: `incident_id`,
incident class and strategy name, detector result, recalled passage/incident refs, the ordered list of
`ObservationRef(evidence_id, capability, status, model_text, sha256)`, decision history, step and usage
counters, `proposal_id`, `approval_id`, `action_id`. Full observation bodies live only in the evidence
store (§16.1). State never holds MCP or provider SDK objects.

**Checkpointing:** `langgraph-checkpoint-postgres` with `thread_id = incident_id`. Recovery re-invokes
the same thread from its last checkpoint. Every node **MUST** be safe to re-execute after a crash that
happens before its checkpoint is written. §14 lists how each node achieves this.

### 10.2 Budgets (enforced in Python, outside model and strategy discretion)

| Budget | Setting | On exhaustion |
|---|---|---|
| Steps per incident | the class's `budgets.steps`, capped by `MAX_STEPS` | stop investigating; `record` → escalate with evidence; audit `access.budget_exhausted` |
| Tokens/cost per incident | the class's `budgets.tokens`, capped by `MAX_TOKENS_PER_INCIDENT` | same |
| Reads per step | `MAX_READS_PER_STEP` *(default 1)* | extra calls ⇒ `InvalidDecision(multiple_calls)` |
| Sub-calls of a combined capability | its spec's `max_subcalls` | remaining sub-calls refused as observations |
| Global daily cost | `MAX_MODEL_COST_PER_DAY` | no model call; escalate with deterministic evidence |
| Per-principal daily cost | `MAX_MODEL_COST_PER_PRINCIPAL_PER_DAY` | that principal's new runs escalate without a model |
| Invalid decisions | counted as steps | same as the step budget |

Every read counts as one step whatever the strategy. LangGraph's recursion limit is only a crash
guard. Budgets, incident status, holds and policy are re-checked after **every** observation and after
every resume.

### 10.3 Diagnostic strategies (`orchestration/strategies`)

```python
class InvestigationView(BaseModel):          # read-only, assembled by the skeleton
    incident: Incident
    incident_class: IncidentClassSpec
    header: IncidentHeader                   # detector findings, alerts, related incidents
    passages: list[Passage]; prior_incidents: list[PriorIncidentSummary]
    observations: list[ObservationRef]       # bodies are loaded by the ContextAssembler on demand
    decisions_so_far: list[AgentDecision | InvalidDecision]
    offered_tools: list[ModelToolDefinition] # already filtered by policy, class tags and level
    remediation_options: RemediationOptions  # from policy; empty while no write is released
    budgets_left: BudgetsLeft

class DiagnosticStrategy(Protocol):
    name: str
    def next_step(self, view: InvestigationView) -> AgentDecision | InvalidDecision: ...
```

**Contract for every strategy:**
- It **only returns a decision**. It never calls capabilities, ports with side effects, the database or
  gateways. The skeleton executes reads through `InvokeCapability`, and proposals through policy and
  human approval. **Safety therefore does not depend on which strategy runs**, and a new strategy
  cannot weaken it.
- It may use the model-tool harness (injected) to ask the model for a decision.
- It must be deterministic given its inputs and the model's reply, so the skeleton can re-run it after
  a crash.
- Budgets, audit and checkpointing belong to the skeleton and apply to every strategy.

**Registered strategies:**

| Strategy | Behaviour | Used by |
|---|---|---|
| `evidence_pack` | returns the fixed Level 1 read list of §10.7, then `Escalate` | unsupported and undiagnosable incidents; the §21.2 baseline |
| `model_loop` | asks the model for each decision (§10.4) until it concludes, escalates or proposes | default for registered classes |
| `plan_then_reason` | returns the class's fixed first round of reads, then continues as `model_loop` | classes whose first evidence is always the same |

Future strategies (for example `hypothesis_checklist`, which confirms or rejects runbook hypotheses one
by one, or `consult_peer`, which asks the security agent through an external tool provider) are
registered the same way. A strategy is selected by the incident class, never by a request.

### 10.4 The `model_loop` contract

1. `investigate` reloads the incident. Evidence attached since the last step (late alerts, manual or
   peer triggers) becomes visible, and `evidence_version` is carried into state.
2. `ContextAssembler` builds a `ModelContext` (§10.6).
3. The harness uses the view's `offered_tools`: capabilities that policy allows for this incident's
   scope, tagged for the class (plus all Level 1 tools), up to `MAX_TOOL_LEVEL` and within the
   tool-definition slot of §10.6. It adds the Argus decision tools (§11.2) and calls `LLMPort.decide`.
4. The harness converts `ModelReply` into exactly one `AgentDecision` or an `InvalidDecision` (§11.3).
5. `InvalidDecision` → audit `decision.invalid` (fabricated tools are also a `security.event`); a
   corrective observation goes back to the model; the budget is charged.
6. `UseReadTools` → `act`. `Conclude`/`Escalate` → `record`. `ProposeRemediation` → `propose_action`.

### 10.5 Recall

- Runbook passages: `KnowledgePort.search(query, k=3)`. The query combines the incident class, the
  target and the salient findings. Each passage keeps its runbook ID and section.
- Prior incidents: `IncidentMemoryPort.similar_incidents(target, incident_class, k=2)`, same target and
  class first. Each includes date, diagnosis and outcome.
- During the investigation, a strategy may request more through the in-worker capabilities
  `knowledge.runbook` and `knowledge.prior_incidents`, which go through `InvokeCapability` like any
  other read.

### 10.6 Context assembly (`orchestration/context.py`)

`ContextAssembler` is deterministic given its inputs. It loads observation bodies from the evidence
store by ID.

| Slot | Bound *(default)* | Rule |
|---|---|---|
| System instructions + policy summary + remediation options | ≤ 1.5k tokens | always present |
| Incident header: class, findings, target, alert labels, related incidents, `evidence_version` | ≤ 0.5k | always present |
| Runbook passages | top-3, ≤ 400 tokens each | ranked by retriever score |
| Prior incidents | top-2, ≤ 250 tokens each | same target/class first |
| Read-tool definitions | ≤ 2k tokens | tools policy allows for this incident's scope, tagged for the class, plus Level 1; never write capabilities |
| Observations | each ≤ 800 tokens; logs ≤ last 50 lines / 8 KiB | keep capability, source host/executor, `observed_at`, truncation flag |
| Older steps | beyond the 4 most recent observations | replaced by each observation's one-line `model_text` |

**Omission order when over budget** (dropped first to last): compacted older observations → the 2nd
prior incident → the 3rd, then the 2nd, runbook passage → the 1st prior incident. **Never dropped:**
system instructions, incident header, current proposal/approval state, latest observation. If the
context still does not fit, the step ends in `Escalate(context_budget_exhausted)`. Silent truncation is
not allowed.

### 10.7 Evidence pack

The evidence pack is the fixed, model-free set of observations collected for an incident that Argus
does not diagnose (`unsupported_escalated`, `undiagnosable`). It lets a human start from facts without
Argus claiming a diagnosis.

- It is configuration: a list of Level 1 capabilities per target kind (for a container: status,
  resources, health, restart count, recent logs; for its host: CPU, memory, disk, uptime; for each
  declared endpoint: an HTTP or TCP probe).
- It runs through `InvokeCapability` with the caller `strategy:evidence_pack`, so every read is
  policy-checked, audited, redacted and stored.
- It has its own small budget and never calls the model.
- The escalation notification links to the stored evidence records.

### 10.8 Redaction and prompt-injection defence

- **One `Redactor`** (`capabilities/redaction.py`) applies to **all** model-bound, stored and
  view-bound text: logs, inspect output, alert labels/annotations, runbook passages, prior-incident
  summaries, probe output, peer findings and human-reported symptoms. It removes key/token/password
  assignments, bearer tokens, credential-bearing connection strings, private keys and high-entropy
  strings above a threshold. It records `redactions=n` on the `Observation`. It runs in the capability
  result path, **before storage**, and again in the assembler.
- **Evidence is data.** Every external text is wrapped with provenance, e.g.
  `<evidence id="…" source="docker-read-gateway@host-t" capability="container.logs" observed_at="…">…</evidence>`.
  The system instructions say that instructions inside evidence must be ignored. Text from a peer
  agent is evidence like any other, never an instruction.
- **Safety does not depend on model obedience.** The model has no authority, remediation choices come
  from policy, and every proposal is re-checked before dispatch.

---

## 11. Model interaction

### 11.1 Model-tool harness (`tooling/model_harness.py`)

This is the bridge between strategies, the model and the tools. It receives an `LLMPort` and a
`ToolCatalogue` by injection. MCP objects stop at `tooling/mcp/`, provider objects stop at the LLM
adapter, and graph state holds only Argus values.

```text
ToolCatalogue.list() ─▶ filter (policy, class tags, level) ─▶ ModelToolDefinition[] ─┐
policy.remediation_options(incident) ─▶ decision tools ─────────────────────────────┼─▶ LLMPort.decide ─▶ ModelReply ─▶ AgentDecision | InvalidDecision
ContextAssembler ─▶ ModelContext ───────────────────────────────────────────────────┘
```

Tools are shown to the model under their `model_name` (e.g. `get_container_status`); the harness maps
them back to the canonical capability name.

### 11.2 Decision tools

Besides the read tools, the harness offers three **Argus-owned decision tools**: `propose_remediation`,
`conclude` and `escalate`. They:

- appear in the model request as tool definitions;
- are **not** in any tool provider, **not** in the dispatcher, and are **never executed**. The harness
  only converts them into `AgentDecision` values;
- are generated per request. `propose_remediation.capability` and `.target` are JSON-schema enums built
  from `policy.remediation_options(incident, target)`, which returns the permitted capabilities,
  targets, argument schemas and runbook-derived preconditions (e.g. "only when `oom_killed=true` and
  `restart_count ≥ 3`");
- when policy permits no remediation (including while no write capability is released, or while the
  target is on hold), `propose_remediation` is **not offered at all**.

### 11.3 Conversion rules (identical for every adapter)

| `ModelReply` | Result |
|---|---|
| 1 to `MAX_READS_PER_STEP` calls, all to offered read tools | `UseReadTools` after argument validation of each call |
| exactly one call to `propose_remediation` / `conclude` / `escalate`, and nothing else | the corresponding decision after validation |
| a call to a write capability name (e.g. `container.restart`) or any unknown name | `InvalidDecision(fabricated_tool)` + `security.event`; **none** of the calls execute |
| arguments fail the schema, target not in the enum or out of scope, or `evidence_refs` not stored for this incident | `InvalidDecision(malformed)`; **none** execute |
| more read calls than `MAX_READS_PER_STEP`, or a decision tool mixed with any other call | `InvalidDecision(multiple_calls)`; **none** execute |
| text only | parsed as JSON `AgentDecision` if possible, otherwise `InvalidDecision(no_decision)` |
| `finish_reason` = `length` / `content_filter` / `error` | `InvalidDecision(provider_*)`; bounded retry, then escalate |

Each provider adapter maps its native format into `ModelReply` and nothing else. A provider without
native tool calling returns the JSON decision in `text`.

---

## 12. Capabilities and tool execution

### 12.1 Registry and policy entries

- `capabilities/registry.py` explicitly imports each area module and assembles the canonical
  `name → (CapabilitySpec, implementation)` map. There is no auto-discovery.
- The policy data file (§13.1) holds one entry per capability. **A capability in the registry but not
  in the policy file is refused (fail closed).**
- Tool providers (§12.5) are configured from the same registry. The MCP tools server publishes only
  specs with `permission="read"` and `runs_in="tools_child"`.
- At startup the registry validates, together with the class and strategy registries: every executor
  named by a spec has a client in the `ExecutorRegistry`; every host that declares an executor has a
  credential for it; every tag used by a class exists. Otherwise Argus refuses to start.

### 12.2 Capability catalogue

Canonical names are dotted; the model sees the `model_name` from the tool roadmap. The level decides
the rollout (`MAX_TOOL_LEVEL`, §13.1).

**Level 1 — basic observation**

| Model name | Capability | Executor | Notes |
|---|---|---|---|
| `get_container_list` | `container.list` | `docker_read` | in-scope containers only |
| `get_container_status` | `container.status` | `docker_read` | state, exit code, OOMKilled, restart count, health; redacted inspect |
| `get_container_resources` | `container.resources` | `docker_read` | `stats?stream=false`; usage vs limits |
| `get_container_logs` | `container.logs` | `docker_read` | tail-bounded, redacted |
| `check_container_health` | `container.health` | `docker_read` | Docker health-check state and last results |
| `get_container_restart_count` | `container.restart_count` | `docker_read` | |
| `get_host_cpu` | `host.cpu` | `host_probe` | |
| `get_host_memory` | `host.memory` | `host_probe` | incl. swap |
| `get_disk_usage` | `host.disk_usage` | `host_probe` | inventory-allowlisted mounts |
| `get_system_uptime` | `host.uptime` | `host_probe` | |
| `check_port` | `network.tcp_connect` | `network_probe` | inventory-allowlisted ports |
| `check_http_endpoint` | `network.http_probe` | `network_probe` | inventory-allowlisted URLs; status + latency |

**Level 2 — diagnosis**

| Model name | Capability | Executor | Notes |
|---|---|---|---|
| `get_memory_history` / `get_cpu_history` / `get_disk_history` / `get_network_history` | `metrics.memory_history` / `.cpu_history` / `.disk_history` / `.network_history` | `prometheus` | named signal templates; bounded window, step and series |
| `get_restart_history` | `metrics.restart_history` | `prometheus` | restart-count and exit-code series from `argus-exporter` |
| `get_top_cpu_processes` / `get_top_memory_processes` | `host.top_cpu` / `host.top_memory` | `host_probe` | top-n, bounded |
| `get_container_processes` | `container.processes` | `docker_read` | `/containers/{name}/top` |
| `get_container_events` | `container.events` | `docker_read` | time-bounded, filtered to in-scope containers |
| `get_detailed_logs` | `container.detailed_logs` | `docker_read` | time-scoped, filtered, bounded, redacted |
| `search_logs` | `container.search_logs` | `docker_read` | fixed or allowlisted patterns over a bounded window |
| `get_directory_sizes` | `host.directory_sizes` | `host_probe` | inspection-policy paths only |
| `get_docker_disk_usage` | `docker.disk_usage` | `docker_read` | `/system/df` reduced to totals |
| `get_kernel_oom_records` | `host.kernel_oom_records` | `host_probe` | kernel OOM-killer records from the journal |
| `check_dns` | `network.resolve_dns` | `network_probe` | |
| `check_connectivity` | `network.connectivity` | `network_probe` | between inventory targets |
| `check_tcp_connection` | `network.tcp_connection` | `network_probe` | repeated attempts + latency |
| `get_socket_summary` | `host.socket_summary` | `host_probe` | counts by state, bounded listing |
| `get_container_network` | `container.network` | `docker_read` | from `/containers/{name}/json` |
| `get_host_load` | `host.load` | `host_probe` | |
| `get_io_metrics` | `host.io` | `host_probe` | |

**Level 3 — deep diagnosis (read)**

| Model name | Capability | Executor | Notes |
|---|---|---|---|
| `inspect_approved_file` | `host.read_file` | `host_probe` | inspection policy (§4.7) |
| `inspect_service_config` | `host.service_config` | `host_probe` | allowlisted configuration paths |
| `get_journal_logs` | `host.journal` | `host_probe` | allowlisted systemd units |
| `inspect_process_details` | `host.process_details` | `host_probe` | |
| `inspect_database_health` | `database.health` | `db_probe` | read-only monitoring role |
| `compare_incident_baseline` | `metrics.compare_baseline` | `prometheus` | same signals over an earlier healthy window; no stored baseline |
| `query_runbook` | `knowledge.runbook` | `argus_internal` | in-worker; `KnowledgePort` |
| `query_prior_incidents` | `knowledge.prior_incidents` | `argus_internal` | in-worker; `IncidentMemoryPort` |
| `capture_diagnostic_snapshot` | `analysis.diagnostic_snapshot` | `argus_internal` | combined (§12.7) |
| `correlate_incident_timeline` | `analysis.timeline` | `argus_internal` | combined; alerts, events, stored evidence |
| `trace_request_path` | `analysis.trace_request_path` | `argus_internal` | combined; follows the inventory dependency graph |

**Write capabilities (`permission="write_hitl"`)**

| Capability | Executor | Status in this release |
|---|---|---|
| `container.restart` | `action_gateway` | registered; **not released** (write gate closed) |
| `service.scale`, `container.update_resources`, `docker.prune`, `logs.rotate`, `service.restart`, `deployment.rollback`, `container.isolate`, `runbook.execute` | `action_gateway` or a dedicated gateway | future; each is added with the write contract (§14.8) and released on its own |

Write capabilities are never offered to the model as tools, never published over MCP, and run only
via proposal → human approval → precheck → ledger.

### 12.3 Capability contract and executor resolution

```python
class CapabilitySpec(BaseModel):
    name: str                         # "network.tcp_connect"
    model_name: str                   # "check_port"
    description: str
    use_when: str                     # "a dependency is suspected unreachable from the target network"
    do_not_use_when: str              # "the metric snapshot already shows the dependency healthy"
    arguments: type[BaseModel]        # → JSON Schema for the model; additionalProperties: false
    target_kinds: set[str]
    level: Literal[1, 2, 3]
    risk: Literal["low", "medium", "high", "very_high"]
    tags: set[str]                    # e.g. {"memory", "container"}; matched against class tool_tags
    executor: str                     # registered executor name: "docker_read", "host_probe", "prometheus", …
    runs_in: Literal["tools_child", "worker"]
    timeout_s: tuple[float, float]    # (default, hard max)
    max_output_bytes: int
    max_subcalls: int = 0             # combined capabilities only
    side_effect: Literal["none", "write"]
    permission: Literal["read", "write_hitl"]

class Observation(BaseModel):
    observation_id: str               # becomes the evidence_id when stored
    status: Literal["ok", "error", "timeout", "refused"]
    capability: str
    target: TargetRef
    host: str                         # "host-t"
    executor: str                     # "network_probe"
    observed_at: datetime
    duration_ms: int
    values: dict[str, JsonValue]      # structured, capability-specific
    error_category: Literal["none", "unreachable", "timeout", "not_found", "forbidden",
                            "invalid_args", "upstream_error", "internal"] = "none"
    truncated: bool = False
    original_bytes: int | None = None
    redactions: int = 0
    model_text: str                   # concise one-line rendering derived from the fields above

def tcp_connect(args: TcpConnectArgs, client: NetworkProbeClient) -> Observation: ...
```

**Executor resolution** (in `tooling/dispatch.py`, on every call):

```text
spec.executor = "host_probe"   +   target.host = "host-t"
  → InventoryPort: hosts["host-t"].executors["host_probe"] = http://<host-t private IP>:8702
  → settings: credential for ("host-t", "host_probe")
  → ExecutorRegistry: "host_probe" → HostProbeClient
  → HostProbeClient(url, credential) passed to the implementation
```

- A host that declares no endpoint for the executor yields `Observation(status="refused",
  error_category="not_found")`. There is **never** a fallback to another host.
- Executor endpoints are configuration (inventory); credentials are settings keyed by
  `(host, executor)`. Nothing about executors is stored in the database except the `host` and
  `executor` recorded on each evidence and audit row.

**Rules for every capability implementation:**
- It returns an `Observation`. Expected failures become `status="error"|"timeout"` with an
  `error_category`; exceptions are only for programming errors.
- It never decides authorization, never reads configuration directly (clients are injected), and never
  writes audit or evidence. `InvokeCapability` does both.
- It enforces its own timeout and output bounds, and applies redaction before returning.
- The MCP server serializes exactly this `Observation` and the client deserializes it, so the MCP and
  in-worker paths look identical to the caller.

### 12.4 `InvokeCapability`: the single guarded entry point

```python
class CapabilityRequest(BaseModel):
    incident_id: IncidentId
    caller: str                        # "model", "strategy:<name>", "capability:<combined name>", principal id
    principal: Principal | None        # when a human or peer is the origin
    name: str
    arguments: dict

InvokeCapability(request) -> Observation
```

```text
1. resolve spec (unknown or write name ⇒ refused + security.event)
2. validate arguments against the spec schema          ── invalid ⇒ Observation(refused, invalid_args)
3. check budgets and incident status                    ── exhausted/closed ⇒ refused
4. audit tool.requested
5. policy.check(capability, args, incident, caller)     ── refused ⇒ audit tool.refused ⇒ Observation(refused)
6. ToolCatalogue.call(name, args)  → provider → dispatch → executor → capability
7. redact (again) and bound
8. store EvidenceRecord (insert-only)
9. audit tool.completed | tool.failed, referencing evidence_id
10. return the Observation (usable only if 8 and 9 succeeded)
```

- **Ordering is mandatory:** policy runs after a concrete capability and arguments are chosen, and
  before execution. A denied request never reaches a provider, a network call or a notification.
- Evidence is written before the audit record that references it. If the audit write fails, the
  observation is discarded; the orphan evidence row is never referenced and is harmless. No
  transaction spans two ports.
- Every caller — the `act` node, the evidence pack, combined capabilities, the peer adapter — goes
  through this path. An import/call-site test enforces it (§2.3 rule 9).

### 12.5 `ToolCatalogue` and tool providers

```python
class ToolCatalogue(Protocol):          # owned by application/
    def list(self) -> list[CapabilitySpec]: ...
    def call(self, name: str, args: dict, target: TargetRef) -> Observation: ...
```

The production catalogue aggregates **tool providers**. The registry remains the single source of
truth; providers only decide *where* a capability runs.

| Provider | Runs | Serves | Holds |
|---|---|---|---|
| `McpChildProvider` | stdio MCP tools server, child of the worker, UID `argus-tools` | `runs_in="tools_child"`: container, host, network, database and metrics-history reads | Host T executor credentials only |
| `InWorkerProvider` | inside the worker | `runs_in="worker"`: knowledge lookups and combined capabilities | injected `KnowledgePort`, `IncidentMemoryPort`, and an invoker bound to `InvokeCapability` |
| `ExternalMcpProvider` *(future)* | remote MCP client | a peer agent's or external server's tools, each with a registry spec and policy entry | that peer's credential |

`TOOL_CATALOGUE=mcp|direct` selects, for the tools-child set, the stdio MCP server or a direct
in-process registry (tests, and the fallback of OD-3). Orchestration and tests do not change.

**MCP tools server (`tooling/mcp/tools_server.py`):**
- Transport is **stdio only** (or an in-process transport in tests). There is **no TCP/HTTP listener**,
  so MCP adds no network route.
- It publishes only read capabilities with `runs_in="tools_child"`.
- It rejects names that are not published, re-validates argument shape and the **static deployment
  target scope**, then delegates to `dispatch.py`.
- It never owns incident-aware authorization, approval, audit or evidence storage. Those stay in
  `policy/` and `InvokeCapability`.

**Why MCP is used here:**
1. process and credential isolation of target-side read execution (§12.6);
2. a tested contract for external and peer tool providers (§23);
3. it is a stated course learning objective.

Its retention is decided by a benchmark (**Open Decision OD-3**, §25).

### 12.6 Local process identity for the tools server

- The tools server is spawned by `argus-worker` as a child process under a dedicated non-root UID
  (`argus-tools`), dropped at spawn (`setpriv`/`gosu`).
- Executor credentials (read gateway, probes, Prometheus if protected) are mounted read-only, mode
  `0400`, owned by `argus-tools`. The worker UID cannot read them, and the api/scheduler containers
  never receive them.
- The tools server holds **no database credential**. That is why knowledge and memory lookups run in
  the in-worker provider.
- The action-gateway credential is mounted only for the worker write path, and only after a write
  capability is released.
- The tools server writes nothing to disk. The worker container shares no PID/IPC namespace with
  other containers.

### 12.7 Combined capabilities

Combined capabilities (`analysis.*`) run in the worker and gather several observations into one
result, for example a diagnostic snapshot or a request-path trace.

- They receive an **invoker bound to `InvokeCapability`** for the current incident, with the caller
  `capability:<name>`. Every sub-call is individually validated, budgeted, policy-checked, audited and
  stored. A combined capability can never reach an executor directly.
- A spec declares `max_subcalls`; further sub-calls are refused as observations.
- The combined result is itself stored as evidence and references its sub-observations by
  `evidence_id`.

### 12.8 Write dispatch (`tooling/local_write.py`)

Writes never go through MCP, a tool provider or `InvokeCapability`. `local_write.py` is called only by
`execute_write`, after a successful `precheck_action`. It calls the write capability's `dispatch`
(§14.8), which sends the capability's exact route with `X-Argus-Action-Id` to the action gateway on the
target's host, and returns an `Observation`.

---

## 13. Policy and safety

### 13.1 Policy as versioned data

The **policy rules are data** in `config/policy.yaml`, versioned in Git and reviewed like code. The
`argus/policy` package is only the **evaluation engine** (domain-only imports). Adding a capability, a
target or an approver scope changes the data file, never the engine.

```yaml
max_tool_level: 3                       # rollout control: 1, 2 or 3
target_scopes:
  shop-ops: [host-t/container:shop-api, host-t/container:shop-nginx, host-t/database:shop-db]
capabilities:
  container.logs:     {scopes: [shop-ops], max_per_incident: 10}
  host.read_file:     {scopes: [shop-ops], max_per_incident: 5}
  container.restart:  {scopes: [shop-ops], requires_approval: true, approver_scope: shop-ops,
                       max_per_incident: 1, preconditions: ["restart_count >= 3"]}
never_write:                             # e.g. RB-003: never restart the dependent service
  - {class: dependency_unavailable, capability: container.restart, target: dependent}
inspection: { … }                        # §4.7
approvers:
  shop-ops: {roles: [approver], principal_kind: human}
write_gate:
  open: []                               # (capability, target) pairs released per §22.2; empty in this release
holds:
  who_may_place: [operator, approver, peer_agent]
```

- `policy_version` is the SHA-256 of the loaded file. It is recorded on every audit record and bound
  into every proposal digest.
- The file is validated at startup against the capability, class and inventory registries: unknown
  capabilities, scopes or targets refuse startup.
- **Fail closed:** a capability without an entry is refused; a target outside every scope is refused.

| Engine component | Decides |
|---|---|
| `engine.py` | loads and validates the data file; computes `policy_version` |
| `scope.py` | whether the target is in the deployment scope and in the incident scope (target + inventory neighbours) |
| `checks.py` | `policy.check(capability, args, incident, caller) -> PolicyDecision(allowed, rule, reason)`; fail closed |
| `inspection.py` | whether a path, log range or process read is allowed for the target (§4.7) |
| `remediation_options.py` | which remediations may be proposed for this incident/target |
| `approvers.py` | whether a principal may approve a given proposal (always a `human` principal) |
| `holds.py` | whether an active hold forbids a write on the target |
| `write_gate.py` | whether a `(capability, target)` pair is released; default closed |

`policy.check` for a write returns *allowed-pending-approval*, never plain *allowed*.
`max_per_incident` counts actions in states `attempting`, `confirmed` and `indeterminate`. Capabilities
above `max_tool_level` are refused and never offered.

### 13.2 Enforcement order

```text
decision (from any strategy; untrusted if model-produced)
  → harness conversion + Pydantic validation          well-formed decision within the per-step limits?
  → step / token / daily / per-principal budget         within hard limits?
  read     → InvokeCapability: audit requested → policy.check → provider → capability
             → redact → store evidence → audit result → Observation
  proposal → write gate released for (capability, target)? (no ⇒ escalate)
           → no active hold on the target?                 (hold ⇒ escalate)
           → immutable proposal (target identity, policy and inventory versions)
           → approval + outbox (one tx) → await_approval (consume early answer | interrupt)
           → authenticated human, scoped, digest-bound, atomic answer + resume intent
           → precheck (digest, incident open, current policy, hold, target identity,
                       inventory version, evidence version, expiry)
           → ledger attempting → action gateway (action_id)
           → ledger confirmed | failed | indeterminate → fresh verification → record
```

### 13.3 Write gate

Two independent controls make each write capability impossible until its release criteria in §22.2
pass:

1. **Policy:** a `(capability, target)` pair absent from `write_gate.open` is denied,
   `propose_remediation` is not offered for it, and no approval is ever requested. A write proposal
   reaching `propose_action` for it ends as `no_action_escalated`.
2. **Deployment:** the action gateway has no route for it, or the gateway is not deployed, its firewall
   rule from Host A is closed and the worker has no action credential.

Releasing a pair is a reviewed deployment change: the policy file entry, the gateway route, the
credential and the firewall rule, together. It is never a runtime toggle reachable through the API or a
peer. **In this release `write_gate.open` is empty: Argus is read-only.**

### 13.4 Required behaviours

| Situation | Behaviour |
|---|---|
| Model invents a capability or calls a write name directly | refused; audited as a security event; corrective observation; budget charged |
| More read calls than allowed in one reply, or a decision mixed with other calls | none executed; observation; budget charged |
| Invalid arguments | refused before transport; the strategy may correct; budget charged |
| Unauthorized or out-of-scope target | refused before any provider call or notification |
| Capability above `max_tool_level` | not offered; refused if requested |
| Combined capability exceeds `max_subcalls` | remaining sub-calls refused as observations |
| Remediation proposed while its pair is not released | no approval; escalate with evidence |
| Remediation proposed on a held target | no approval; escalate with evidence and the hold |
| A service or agent principal tries to answer an approval | refused; audited as a security event |
| Approval never arrives | atomic expiry ⇒ `expired` ⇒ escalate; never auto-approve |
| Late or double answer | zero-row transition; audited no-op; no resume intent |
| Proposal changed, target replaced, incident resolved, proposal expired, inventory changed, hold placed, or approver lacks scope | rejected at answer time or at precheck; a new proposal needs a new approval |
| Approved action fails | ledger `failed`; no blind retry; verification still runs; escalate |
| Crash during dispatch | reconcile (§14.5); unknown ⇒ `indeterminate` ⇒ escalate |
| Verification sees only a pre-action sample | keep polling until a fresh sample arrives or timeout ⇒ escalate |
| Docker inspect contains secrets | redacted before the Observation |
| Another process tries to reach the MCP server | no listener; stdio child reachable only by its parent |
| A peer request carries instructions in its finding | stored as redacted evidence; never executed as instructions |

### 13.5 Target holds

A **target hold** forbids every write on a target while it is active, for example to preserve forensic
evidence while the security agent examines a compromised container.

- Holds are placed and released through `PlaceTargetHold` / `ReleaseTargetHold` by principals the
  policy file allows (operators, approvers, peer agents). Every change is audited.
- A hold never blocks reads. It is checked when proposals are generated, at `propose_action` and again
  at `precheck_action`.
- A hold may carry an expiry. An expired hold is inactive; it is never deleted.

---

## 14. Human-in-the-loop: approval → resume → action state machine

This machinery is **generic over write capabilities**. The capability-specific parts are supplied
through the write contract (§14.8). In this release no write capability is released, but the machinery,
its tables and its tests exist from the start so that the first release changes no core code.

### 14.1 Tables (Postgres)

| Table | Key fields | Mutability |
|---|---|---|
| `action_proposal` | `proposal_id`, `incident_id`, `capability`, `target` (host, kind, name), `target_identity_json`, `arguments_json`, `evidence_refs_json`, `evidence_version`, `policy_version`, `inventory_version`, `created_at`, `expires_at`, `digest` | insert-only (runtime role has no UPDATE) |
| `approval` | `approval_id`, `proposal_id`, `proposal_digest`, `state`, `approver_scope`, `actor`, `requested_at`, `expires_at`, `answered_at` | forward transitions only |
| `notification_outbox` | `key` (PK, e.g. `approval_id`), `channel`, `payload`, `attempts`, `next_attempt_at`, `last_result`, `delivered_at` | worker-updated |
| `resume_intent` | `approval_id` (PK), `incident_id`, `decision`, `state` (`pending/done/failed`), `attempts`, `last_outcome` | worker-updated |
| `action` | `action_id`, `proposal_id`, `approval_id`, `state`, `attempted_at`, `result_at`, `evidence` | forward transitions only (CHECK/trigger) |
| `target_hold` | `hold_id`, `target`, `reason`, `placed_by`, `placed_at`, `expires_at`, `released_by`, `released_at` | insert + a single release transition |

### 14.2 States

```text
approval:  pending ──approve──▶ approved
              ├──── deny ─────▶ denied
              ├──── expire ───▶ expired
              └──── invalidate▶ cancelled      (contradictory evidence / incident closed / hold placed)

action:    unstarted ─▶ attempting ─▶ confirmed       (gateway/Docker reported success)
                              ├────▶ failed          (definite failure; the action did not happen)
                              └────▶ indeterminate   (outcome cannot be established)
```

### 14.3 What the approver sees and how answers are accepted

- The notification and the approval view show the **proposal itself**: capability, target (host, kind,
  name) and its identity, arguments, rationale, evidence references and expiry.
- Only a principal of kind **`human`** can answer. In this release the approver authenticates to the
  API (JWT, §17.3) and answers through Swagger or the CLI. When Slack is added, a **signed single-use
  link** scoped to exactly `approval_id + proposal_digest` becomes a second path; its expiry is no
  later than the approval's, and it becomes unusable after any terminal answer. Opening the link shows
  the proposal; answering requires an explicit POST, never a GET.
- The approver must pass `policy/approvers.py` for this capability and target. If not, the answer is
  refused and audited.
- `actor` is derived server-side.
- The answer and the resume intent commit **atomically**:

```sql
BEGIN;
UPDATE approval
   SET state = 'approved', actor = :authenticated_actor, answered_at = now()
 WHERE approval_id = :id AND state = 'pending' AND expires_at > now()
   AND proposal_digest = :digest_shown_to_approver;
-- only if exactly one row changed:
INSERT INTO resume_intent (approval_id, incident_id, decision, state, attempts)
VALUES (:id, :incident_id, 'approved', 'pending', 0)
ON CONFLICT (approval_id) DO NOTHING;
COMMIT;
```

Deny uses the same pattern. The expiry sweeper (a worker loop) performs `pending → expired` plus a
resume intent, so the graph records the outcome and escalates.

### 14.4 Sequence and crash points

| # | Step (one transaction unless noted) | Crash here ⇒ recovery |
|---|---|---|
| 1 | `propose_action`: capture `identity(target)`; insert `action_proposal` | node reruns; insert keyed by `(incident_id, step)` is idempotent |
| 2 | `request_approval`: insert `approval(pending)` + `notification_outbox` | node reruns; `ON CONFLICT DO NOTHING` |
| 3 | `DeliverNotifications`: send (external), then set `delivered_at` | resent with the same link/token (at least once); duplicates harmless |
| 4 | `await_approval`: read the approval; terminal ⇒ consume; else `interrupt()` | checkpoint replays the node; same check |
| 5 | Answer: atomic transition + `resume_intent` | intent is durable; API death after commit loses nothing |
| 6 | `ResumeAnsweredApprovals`: `runner.resume`; `resumed`/`already_past` ⇒ intent `done`; `not_yet_waiting` ⇒ retry with backoff; after `RESUME_MAX_ATTEMPTS` ⇒ `failed` + escalate | retried until the checkpoint confirms progress |
| 7 | `precheck_action`: digest matches; incident still open; `policy.check` under the **current** policy; no active hold; `identity(target)` equals the proposal's `target_identity` (via the read gateway or probe); inventory version unchanged; evidence version unchanged or compatible (§14.6); not expired | any mismatch ⇒ approval `cancelled`, audit, re-investigate or escalate |
| 8 | Ledger: `action(unstarted)` → `attempting` + audit `action.attempting` | crash before commit: nothing sent; proceed once |
| 9 | `dispatch(action_id, args)` to the action gateway (external) | reconcile (§14.5) |
| 10 | Ledger `attempting → confirmed \| failed` + audit | reconcile (§14.5) |
| 11 | `verify` → `record` | reads only; safe to rerun |

The per-target execution lock is held from step 7 until step 10 (or `indeterminate`), keyed by the
action's target. A fast answer (before step 4 pauses) is consumed by `await_approval` on entry, and the
resumer then gets `already_past`, so the graph advances exactly once.

### 14.5 Reconciling an `attempting` action on recovery (before anything else)

1. `GET /actions/{action_id}` on the action gateway:
   - *not received* ⇒ the request never reached Docker ⇒ dispatch the **same** `action_id` once (the
     gateway still refuses a second acceptance);
   - *received with a result* ⇒ record `confirmed` or `failed`.
2. If the gateway is unreachable or its answer is ambiguous, call the capability's
   `reconcile(action_id, attempted_at)` (§14.8), which inspects the target through read executors only.
   For `container.restart`: same container ID and `State.StartedAt > attempted_at` ⇒ `confirmed`.
3. Otherwise ⇒ `indeterminate`: audit, stop and escalate with all evidence. **No automatic second
   attempt.** Any further write requires a new proposal and a new approval.

### 14.6 Evidence changes during approval

`precheck_action` compares the proposal's `evidence_version` with the incident's current one:

- unchanged → proceed;
- changed but compatible (same class, target still unhealthy on a fresh snapshot) → proceed and record
  the new evidence on the action;
- contradictory (detector now healthy, a different class, or a different target named) → cancel the
  approval and invalidate the proposal. The incident is re-investigated, escalated, or split into a new
  incident.

If all fingerprints resolve while an approval is pending, precheck finds the incident no longer open,
nothing is dispatched, and the outcome is `resolved_externally`.

### 14.7 Notification delivery (`DeliverNotifications`)

- The worker loop claims due outbox rows, calls `NotificationPort.notify(notification, key)` and
  records the result. On failure it retries with backoff and the same link/token. Delivery failure is
  audited and **never** approves anything.
- Adapters with `dedupes_by_key=True` (Slack, using the key as the message/update key) suppress
  duplicates. Email and generic webhooks may deliver duplicates, which are harmless because the
  answer transition has a single winner.
- In this release the channel is the recording adapter: pending approvals are found through
  `GET /api/v1/approvals?state=pending`.

### 14.8 The write-capability contract

Every write capability implements this contract (`capabilities/write_contract.py`). The proposal,
approval, precheck, ledger, reconciliation and verification machinery above calls it and is otherwise
unchanged when a new write capability is added.

```python
class WriteCapability(Protocol):
    spec: CapabilitySpec                                      # permission="write_hitl"
    def identity(self, target: TargetRef) -> dict: ...        # fingerprint of what is acted on (read executors only)
    def dispatch(self, action_id: str, target: TargetRef, args: BaseModel) -> Observation: ...
    def reconcile(self, action_id: str, target: TargetRef, attempted_at: datetime
                  ) -> Literal["confirmed", "failed", "unknown"]: ...
    verification_signals: set[str]                            # what must be healthy on fresh samples
    reversible: bool                                          # shown to the approver
```

| Element | `container.restart` |
|---|---|
| `identity` | `{"container_id": …}` from the read gateway |
| `dispatch` | `POST /containers/{name}/restart` with `X-Argus-Action-Id` |
| `reconcile` | gateway journal first; then same container ID and `StartedAt > attempted_at` |
| `verification_signals` | the incident class's verification signals, re-run through the detector |

---

## 15. Verification, recording and memory

### 15.1 Post-action verification

- `verify` waits at least one Prometheus scrape interval, then polls `MetricsPort.snapshot` for the
  write capability's `verification_signals` and the incident class's verification signals, with a
  bounded timeout (`VERIFY_TIMEOUT`), until `MetricSnapshot.observed_at > action_completed_at`.
  **A pre-action sample never counts as recovery.**
- It then re-runs the class's detector on the fresh sample: healthy ⇒ `recovered_verified`; still
  unhealthy or timeout ⇒ escalate (`action_failed` if the ledger says `failed`; otherwise escalation
  with the verification evidence).
- Verification runs even when the action failed, so the incident record states the real end state.
- The record distinguishes **service recovery** (symptom gone) from **root-cause resolution** (the
  diagnosed cause removed). A restart may recover a service while the cause remains; the summary says
  so explicitly.

### 15.2 Recording, escalation and routing

`record` sets the incident's final `status` and `outcome` (§5.3), writes an episodic summary
(diagnosis, root-cause target, evidence refs, proposal/action/verification result) through
`IncidentMemoryPort`, and, for every escalation, enqueues a notification to the **routing target**.

**Routing** is data (`config/routing.yaml`): per class family, per unsupported alert name, or per
class `owner`, the escalation goes to a human channel or to a peer agent (§23). The default target is
the operators' channel.

*Implementation choice:* escalation notifications SHOULD reuse the notification outbox, keyed by
`incident_id + "escalation"`.

Only `recovered_verified` counts as Argus remediation success. `resolved_externally` and `diagnosed`
are reported separately.

### 15.3 Memory and knowledge

| Kind | Store | Access | Notes |
|---|---|---|---|
| Episodic memory (past incidents and outcomes) | Postgres | `IncidentMemoryPort.similar_incidents` | same target/class first; redacted summaries only |
| Evidence | Postgres, insert-only | `IncidentMemoryPort` evidence methods | one record per observation; referenced by ID + hash |
| Runbooks | library v1.1.0 in `argus/runbooks/`, versioned in Git | `KnowledgePort.search` (TF-IDF) | improving the corpus comes before changing the retriever |
| Working memory of a run | graph state + checkpoints | orchestration only | evidence references and counters; bounded by §10.6 |

**Runbook corpus rules** (from the library's integration requirements):
- The runbook ID and version come from each file's metadata block (`id: RB-001`), never from the file
  name.
- Passages are bounded and coherent. A retrieved diagnostic or action passage always travels with the
  runbook's scope, available-versus-missing tools, action constraints and verification sections.
  Silent truncation of action guidance is not allowed: the retriever returns a complete bounded
  passage or refuses it.
- The shared contracts (`RUNBOOK-CONVENTIONS.md`) are pinned in context or embedded at indexing; a link
  alone is not evidence that the model received them.
- Authoring, reference and backlog documents (index, assessment, reviews, capability gaps) are not
  indexed for action-oriented retrieval.
- A name marked `MISSING TOOL REQUIREMENT` in a runbook is **never** offered or treated as a tool.
- A runbook's `detector` metadata names the class that uses it (for example `container_restart_loop`
  for RB-001 and RB-008).

No vector store is part of the architecture. A future retriever plugs in behind `KnowledgePort`
(§24), and only once §21 shows TF-IDF recall is insufficient.

---

## 16. Persistence and state management

### 16.1 Inventory of state

All Argus-owned durable state lives in **one Postgres 16 instance on Host A**, split into separate
tables and abstractions:

| # | Category | Contents | Technology | Owner | Retention |
|---|---|---|---|---|---|
| 1 | Graph execution state | checkpoints, interrupts; evidence **references** only | `langgraph-checkpoint-postgres` | orchestration | per incident; prunable after close |
| 2 | Intake, incident and trigger data | intake queue, incidents, trigger occurrences, alert occurrences, related-incident links, `evidence_version` | Postgres | application | months |
| 3 | Evidence | `evidence` table: redacted, bounded, insert-only records with SHA-256 (§5.4) | Postgres | application | per evidence kind; never before the incident closes and its checkpoints are pruned |
| 4 | Episodic, approval and action state | summaries, proposals, approvals, holds, resume intents, outbox, actions, per-target locks | Postgres | application | months/years |
| 5 | Principals | human users (Argon2 password hashes), agent clients (hashed secrets), roles, scopes, disabled flag | Postgres | authentication adapter | while active + audit period |
| 6 | Knowledge | runbooks | Markdown in Git + TF-IDF index built at startup | versioned with code | — |
| 7 | Configuration | inventory, policy, signals, routing, schedules | YAML in Git; SHA-256 versions recorded on proposals and audit | versioned with deployment | — |
| 8 | Audit | all events in §5.7 | Postgres append-only (+ optional JSONL copy) | audit sink | longest of all |
| 9 | Metrics | target and Argus time series | Prometheus TSDB on each Host T | operations | operational |
| 10 | Application logs | structured logs | stdout + Docker log rotation | operations | operational |

SQLite is permitted **only** for single-process local tests. Any deployment where API and worker run
concurrently uses Postgres.

**Evidence trade-offs, accepted deliberately:** one extra insert per capability call; checkpoints are
not self-contained (evidence and checkpoints share one database and one backup, and are pruned
together per incident); redacted evidence is retained, so a redaction miss becomes a stored leak — hence
retention limits per kind, role-scoped views, scoped peer access and redaction fixtures run against
stored rows (§21.1).

### 16.2 Database roles and permissions

- **Schema owner / migration role:** used only by migrations (`deploy/migrations/`).
- **Runtime role(s):** on audit and evidence tables, `INSERT` plus the minimum `SELECT`, and **no
  UPDATE or DELETE** (retention runs under a separate maintenance role). On `action_proposal`, no
  UPDATE. On `approval`, `action` and `target_hold`, updates only through the forward-transition rule
  (CHECK constraint or trigger).
- Runtime credentials are separate from migration and maintenance credentials.

### 16.3 Concurrency primitives

| Need | Mechanism |
|---|---|
| Intake claim | row claim with lease (`FOR UPDATE SKIP LOCKED` or equivalent) |
| Approval race | single conditional `UPDATE … WHERE state='pending' AND expires_at > now()` |
| Idempotent inserts | unique keys + `ON CONFLICT DO NOTHING` (trigger identity, `approval_id`, outbox key, resume intent, evidence ID) |
| Per-target write exclusion | a per-target lock row (or advisory lock) keyed by `host/kind:name`, held from precheck to ledger result |
| One active run per target | checked at claim time by the scheduling policy |

*Implementation choice:* plain SQL or SQLAlchemy (**OD-9**); the migration tool.

### 16.4 Never stored or exposed

Application business rows; credentials or secrets in incident, evidence, audit, model context or
views; raw `Config.Env`; container filesystems or archives; unbounded full logs; plaintext passwords or
client secrets.

---

## 17. Security model

### 17.1 Layers

| # | Layer | Mechanism |
|---|---|---|
| 1 | Caller authentication | Alertmanager bearer token; human login ⇒ short-lived JWT; agent client credentials ⇒ JWT; (later) signed single-use approval links |
| 2 | Authorization | policy data + engine decide capability, target, scope and limits; fail closed; read-view roles (§6.7) |
| 3 | Single entry point | every capability call through `InvokeCapability`; enforced by a call-site test |
| 4 | Model and strategy boundary | Pydantic validation; per-step limits; hard budgets; redaction; evidence as data; strategies return decisions only |
| 5 | Tool boundary | stdio-only MCP; read-only published set; static scope checks; separate UID and credentials; no database credential in the child |
| 6 | Host access | exact-route Docker gateways; inspect redaction; target-side probe verbs; inspection policy; no Docker socket |
| 7 | Cross-host path | private network, private-address binding, `DOCKER-USER` source rules, per-service credentials; tunnel/TLS when leaving the private network |
| 8 | Human approval | authenticated **human** approver; scoped; digest-bound; atomic transition with resume intent |
| 9 | Pre-dispatch re-authorization | proposal digest, incident status, current policy, holds, target identity, inventory version, evidence version, expiry |
| 10 | Action ledger | `indeterminate` ⇒ escalate, never an automatic retry |
| 11 | Write gate | per `(capability, target)` release in policy **and** in the action-gateway configuration |
| 12 | Peer boundary | peers authenticate as agent principals; no write authority; scoped reads; quotas; loop protection (§23) |
| 13 | Audit integrity | DB permissions enforce append-only |

### 17.2 Identities and credentials

| Identity | Used by | Holds |
|---|---|---|
| Alertmanager service identity (per Host T) | Alertmanager → `/api/v1/alerts` | bearer token file; compared in constant time |
| Human principals (`viewer`, `operator`, `approver`) | HTTP/CLI | username + Argon2 password hash in Postgres |
| Peer-agent principals (`peer_agent`) | peer adapter | client ID + hashed client secret in Postgres (mTLS optional later) |
| JWT signing key | api | signs access tokens (HS256); rotated by deployment |
| Approval link signing key *(when Slack is added)* | api | signs single-use approval links |
| Scheduler service identity | scheduler → api | internal credential |
| `argus-tools` UID | MCP tools server | executor credentials per `(host, executor)` |
| Worker write identity | `local_write.py` | action-gateway credential per host (after a release only) |
| Model provider key, notifier credentials | worker | egress credentials |
| DB runtime / maintenance / migration roles | api, worker, scheduler / retention job / migrations | see §16.2 |

All secrets are injected by the deployment (environment or mounted files), read only by
`infrastructure/settings.py`, and passed to adapters by `wiring.py`. They are never logged, audited,
stored as evidence or sent to the model.

### 17.3 Human and agent authentication

- `POST /api/v1/auth/token` implements the OAuth2 password flow for humans and the client-credentials
  flow for agents. It verifies the password (Argon2) or client secret and returns a **JWT** signed with
  HS256, lifetime `ACCESS_TOKEN_TTL` *(default 30 min)*, with claims `sub`, `kind`, `role`, `scopes`,
  `iat`, `exp`, `jti` and `aud="argus-api"`. There are no refresh tokens: the caller logs in again.
- **Read-only tokens (ACR-0001).** The login may ask for `scope=read` (the OAuth2 form field). The JWT then
  carries `access: "read"` (otherwise `access: "full"`). This claim is separate from `scopes` (the target-scope
  names) and can only **narrow** what the role allows: a read token is refused with 403 on every route that is
  not a `GET`, whatever the role, and the refusal is audited (`access.read_only_refused`). User interfaces are
  separate clients of the API and hold only the user's own short-lived token, never a server secret.
- Every request re-reads the principal's `disabled` flag, so disabling a user takes effect before the
  token expires.
- The JWT only proves **who** is calling. What the caller may do is decided server-side by the use
  cases and the policy engine. `actor` is always taken from `sub`.
- Swagger UI (`/docs`) exposes an **Authorize** button for this flow and is the approval console of
  this release. It is served only on the loopback listener.
- Users and agent clients are created with `argus user …` from a shell on Host A. There is no
  self-registration and no user-management API.
- Failed logins are rate-limited and audited (`access.login_failed`).
- *Future:* replacing local users with a single-sign-on provider (OIDC, RS256 + JWKS) changes only
  token verification in `adapters/inbound/http/auth.py`; the `Principal` contract stays.

---

## 18. Observability, logging and audit

### 18.1 Separation rule

Telemetry (metrics, logs, traces) may be sampled, dropped, disabled or reset. **Audit may not.** They
travel different paths (`observability/` vs `AuditSinkPort`) and have different retention. Failing to
emit telemetry never fails an investigation; failing to write audit **MUST** stop the action it
precedes. Tracing a tool call in Langfuse/OpenTelemetry never substitutes for its audit record.

### 18.2 Argus metrics (`prometheus_client` on `/metrics`)

Use multiprocess mode when more than one process exports.

| Signal | Form |
|---|---|
| Webhook requests | counter by status/result + log line |
| Alerts processed / truncated | counters |
| Unsupported incidents, **by alert name and target kind** | counter (the backlog of classes to register, §1.3) |
| Incidents by class, strategy and outcome | counters |
| Incidents created / closed / escalated, by outcome | counters (+ incident rows) |
| Graph execution duration, per target | histogram (also sets the cadence floor, §6.5) |
| LLM calls, tokens, cost; budget terminations | counters (+ optional trace spans) |
| Tool calls and failures, by capability, executor, host and caller | counter **and** audit |
| Evidence records written; evidence-pack runs | counters |
| Rejected actions / refusals | counter **and** audit |
| Approval waiting time | histogram (+ incident timestamps) |
| Action ledger states (`confirmed/failed/indeterminate`) | counter **and** audit |
| Resume-intent and outbox backlog (count, oldest age) | gauges |
| Coalesced / stale-skipped scheduled ticks | counters |
| Graph exceptions | counter + log with `incident_id` |
| Peer requests received / refused, by principal | counters **and** audit |
| Active target holds | gauge |
| Failed logins | counter **and** audit |
| Argus up | scrape health |

### 18.3 Logging

Structured JSON to stdout, and every line inside an investigation carries `incident_id` and
`correlation_id`, so a log line, a metric spike, an audit record and a peer agent's records can be
joined. Logs pass through the `Redactor`. Stack traces
go to logs, never to the model or to user-visible views.

### 18.4 Alert rules on Argus itself (exactly four)

1. Argus scrape target down.
2. Webhook error ratio above threshold for 5 minutes.
3. Approvals waiting longer than the expiry window.
4. A resume intent or outbox item older than 5 minutes, or any action in `indeterminate`.

A separate monitoring-of-monitoring rule (outside Argus) SHOULD detect Alertmanager unavailability.

### 18.5 Tracing

This is optional. `observability/tracing_langfuse.py` or an OpenTelemetry integration is selected by
`wiring.py`, with `tracing_noop.py` as the default. It is never an application port.

---

## 19. Failure behaviour and retries

| Failure | Required behaviour |
|---|---|
| Prometheus unavailable or stale | detection fails closed; no model call; evidence pack; `undiagnosable`; escalate |
| No registered class matches a reported problem | evidence pack; `unsupported_escalated`; no diagnosis claimed; routed per §15.2 |
| Alertmanager unavailable | alert delivery impaired; scheduled checks continue; monitoring-of-monitoring alerts |
| Argus API unavailable | Alertmanager retries; scheduled slots are idempotent; optional reconciliation replays firing alerts |
| Scheduler unavailable | alert path unaffected; missed slots visible in metrics |
| Duplicate trigger | idempotency key ⇒ `duplicate` occurrence; no new run |
| Persistence unavailable before intake | no 2xx; the caller retries |
| Persistence unavailable mid-run | checkpoint cannot advance; worker resumes after recovery |
| Audit sink unavailable | the pending capability/action does not execute |
| LLM unavailable | bounded adapter retry; then escalate with deterministic evidence |
| Model malformed or looping | `InvalidDecision` observation; budgets charged; hard stop |
| Context does not fit | `Escalate(context_budget_exhausted)` |
| MCP child dies | failed `Observation`; the strategy may choose another tool or escalate; no network fallback |
| Evidence store write fails | observation discarded; the step fails as an observation; no audit reference to a missing record |
| Executor not declared for the target's host | `refused / not_found` observation; never another host |
| Read gateway route outside allowlist | 403 ⇒ refusal observation + audit; no fallback |
| Write on a non-released pair or a held target | refused by policy, and again by the action-gateway configuration |
| Probe unavailable | failed observation; never a Host-A substitute |
| Network partition A↔T | reads fail as observations; writes fail closed; escalate |
| API dies after approval commit | resume intent ⇒ resumer resumes once |
| Answer arrives before the interrupt | consumed by `await_approval`; resumer no-ops |
| Crash after notification accepted, before `delivered_at` | resend with the same link; harmless duplicate |
| Notification provider down | outbox retries with backoff; backlog alert; approval still expires normally |
| Crash after dispatch, before ledger result | reconcile (§14.5); unknown ⇒ `indeterminate` ⇒ escalate |
| Proposal, target or incident changed during pause | precheck rejects; approval cancelled |
| Late contradictory alert | proposal invalidated; re-investigate, split or escalate |
| All fingerprints resolve during approval | no dispatch; `resolved_externally` |
| One of several fingerprints resolves | that occurrence is resolved; incident stays open |
| Scheduled tick while a run is active | `coalesced`; no second run or approval |
| Daily cost ceiling reached | detection continues; no model; escalate |
| A principal's quota reached | that principal's runs escalate without a model; other callers unaffected |
| Peer request loops back (Argus already in `origin_chain`) | `refused` occurrence; audited |
| Peer agent unavailable (outbound) | failed observation or undelivered notification; outbox retries; never blocks the incident |
| Two writes on the same target | per-target lock serializes or refuses |
| Verification sees only old samples | poll until fresh or timeout ⇒ escalate |
| Evidence contains injected instructions or secrets | redacted and wrapped as data; policy and precheck make them ineffective |

**Retry principles:** every retry is either idempotent by key (intake, outbox, resume intent) or
preceded by reconciliation (actions). Writes are **never** retried blindly. Every retry loop has a
bound and escalates when the bound is exhausted.

---

## 20. Configuration and environments

### 20.1 Settings (`infrastructure/settings.py`, one typed object built once)

| Group | Settings |
|---|---|
| Data files | paths of `inventory.yaml` (hosts, executor endpoints, targets), `policy.yaml`, `signals.yaml`, `routing.yaml`, `schedules.yaml` |
| Endpoints | model endpoint, notifier endpoints (all Host T endpoints live in the inventory) |
| Credentials (files/env) | Alertmanager webhook token, JWT signing key, executor credentials per `(host, executor)` (mounted for `argus-tools`), action-gateway credential per host (after a release only), model key, notifier credentials, DB DSNs |
| Model request | model name, timeout, and optional parameters (temperature, response format) omitted when the model rejects them |
| Budgets | `MAX_STEPS`, `MAX_TOKENS_PER_INCIDENT`, `MAX_MODEL_COST_PER_DAY`, `MAX_MODEL_COST_PER_PRINCIPAL_PER_DAY`, `MAX_READS_PER_STEP` *(1)* |
| Authentication | `ACCESS_TOKEN_TTL` *(30 min)*, login rate limit, listener addresses (loopback, private, peer) |
| Peers | `MAX_ORIGIN_CHAIN` *(2)*, peer request rate limits |
| Concurrency | `MAX_ACTIVE_INVESTIGATIONS` *(2)*, worker lease timeout |
| Correlation | `CORRELATION_WINDOW` *(30 min)* |
| Detection / verification | `METRICS_MAX_STALENESS`, `VERIFY_TIMEOUT`, scrape interval |
| Approval | approval/proposal expiry, token lifetime, `RESUME_MAX_ATTEMPTS`, outbox retry/backoff |
| Scheduler | `schedules.yaml` path, `SCHEDULE_MAX_QUEUED_AGE`, `reconcile_firing_alerts.enabled` |
| Context | slot bounds of §10.6 |
| Policy | the policy data file (§13.1); its `write_gate.open` list is empty by default |
| Wiring | `TOOL_CATALOGUE=mcp\|direct`, tracing backend, notifier adapters |

Values without a default here are **OD-7**.

### 20.2 Environments

| Concern | Local development / CI | Production (two hosts) |
|---|---|---|
| Metrics | `FakeMetrics` or local Compose Prometheus | Argus-owned Prometheus on each Host T (node-exporter, cAdvisor, argus-exporter) |
| Model | `MockLLM` / recorded fixtures | selected provider (**OD-1**) |
| Knowledge | TF-IDF runbooks | same |
| Incident/checkpoint store | SQLite (single process) or Postgres test container | Postgres 16 |
| Audit | JSONL/recording sink | append-only Postgres (+ optional JSONL) |
| Notification | `RecordingNotifier` | recording adapter + Swagger approvals in this release; Slack next |
| Alert trigger | `--simulate-alert` with a real captured payload | authenticated Alertmanager webhook |
| Scheduler | fake clock | `argus-scheduler` container |
| Inventory | `inventory_fake.py` or a local YAML emulating two hosts | `config/inventory.yaml` |
| Docker read | fakes / local lab | exact-route read gateway over the private path |
| Docker writes | fake action gateway with journal | absent until a write capability is released; then the exact-route action gateway |
| Host/network/database capabilities | fakes | host-probe, network-probe, db-probe on T |
| Human auth | seeded test users | local users in Postgres, JWT |
| MCP | in-process or stdio fake | stdio tools server under `argus-tools` |
| Tracing | no-op | optional |

**Rules:** the same application code runs everywhere, and only settings, wiring and deploy files
differ. Security boundaries (webhook auth, approval identity, gateway ACLs, private-address binding) are
never replaced by fakes in integration tests. Detectors and the domain stay clock-free; the scheduler
uses an injectable clock.

---

## 21. Testing and evaluation

### 21.1 Test layers

| Layer | Proves | Runs |
|---|---|---|
| Unit | detectors, policy engine over data fixtures, trigger normalization, correlation and related-incident links, approval transition, proposal digest, context assembly, redaction, executor resolution | always |
| Import boundary | the dependency rules of §2.3, including the single entry point (rule 9) and strategies returning decisions only | always, from the first commit |
| Registry validation | every class, capability, strategy, signal, tag, executor, policy entry and inventory reference resolves; startup refuses otherwise | always |
| Contract | each port's fake and real adapter; `InvestigationRunner`; **one `Observation` suite** over every capability (incl. timeout and truncation); **one strategy suite** over every registered strategy (returns only decisions, deterministic replay, respects budgets); **one write-contract suite** over every write capability; evidence-store contract; **decision-conversion suite** over ≥ 2 model adapters/fakes (allowed proposal, fabricated write, malformed args, forbidden target, multiple calls, text-only) | fakes always; real adapters under `integration` |
| Component | skeleton on fakes with each strategy; read audit and evidence storage; evidence pack for unsupported and undiagnosable incidents; approval node ordering; budgets; context refresh after late evidence | always |
| Failure injection | crash points of §14.4 (after approval commit; between notification and interrupt, with a fast answer; before dispatch; after gateway acceptance before the ledger write; after provider acceptance before `delivered_at`); resolution during approval; scheduler ticks during a long run | always (Postgres test container under `integration`) |
| Security | gateway routes; JWT auth and expiry; disabled users; non-human approval refused; approver scope; token reuse; read-view authz; injection and secret fixtures (on model input **and** stored evidence); MCP credential isolation; combined capabilities cannot bypass policy; holds; peer scope, quotas and loop protection; write-gate test | always (fakes); real gateways under `integration` |
| E2E | webhook/manual/scheduled/peer trigger → classification → strategy → (approval) → audit | always with fakes |
| Integration | real Prometheus/exporters, Postgres, gateways/probes, stdio MCP, model smoke test | marked; excluded by default |
| Evaluation | diagnostic quality, safety and cost (§21.2) | marked `eval`; excluded by default |

`pytest` is offline and free by default. Integration tests prove *wiring*. Only the evaluation layer
may support claims about *diagnostic quality*.

### 21.2 Evaluation (`tests/eval/`)

**Dataset:** at least 5 labeled, replayable cases per class (snapshot + alert + tool fixtures +
expected label):

| Class | Expected behaviour |
|---|---|
| Container restart loop (RB-001, RB-008) | correct cause: OOM versus non-OOM crash; proposes `container.restart` only for an allowed, released target |
| Health check failed (RB-002) | correct diagnosis backed by log/inspect evidence; no victim restart |
| Dependency unavailable (RB-003, branches RB-004, RB-009) | dependency diagnosed from the target-side probe; root-cause target identified; no restart of the dependent service |
| HTTP, NGINX upstream, TLS (RB-011, RB-015, RB-016) | failing hop and mechanism identified from probes, logs and configuration |
| CPU, host memory, disk, disk I/O, FD/socket (RB-006, RB-007, RB-005, RB-010, RB-012) | responsible process, container, directory or device identified from history and process evidence |
| PostgreSQL connections, blocking, storage (RB-004, RB-013, RB-019) | responsible client, session or storage category identified; no data touched |
| Docker daemon, clock drift, monitoring blind spot (RB-017, RB-020, RB-014) | control-plane, time-source or telemetry failure identified; stale data never diagnosed as healthy |
| Deployment regression, cascading overload (RB-018, RB-021) | release linkage or overload chain identified; RB-021 only after the core classes pass |
| Unsupported incident | evidence pack collected; `unsupported_escalated`; no diagnosis claimed; no model call |
| Ambiguous evidence | abstain/escalate with evidence; no proposal |
| Stale metrics | `undiagnosable` before any model call |
| Tool failure | continue or escalate; never fabricate the missing observation |
| Forbidden target | no executable proposal; refusal audited |
| Denial / expired approval | no action; escalation recorded |
| Unsuccessful recovery | fresh verification fails; escalate; no blind retry |

**Baseline:** a deterministic workflow (detector → top runbook → a fixed diagnostic set per class →
the runbook-prescribed proposal), run on the same cases. It is implemented as a registered strategy.

**Metrics:** diagnosis accuracy; evidence support (cited refs actually support the conclusion,
rubric-scored); tool-choice precision; unnecessary calls per incident; safe-abstention rate;
unsafe-proposal count; action outcome; latency p50/p95; cost per incident; retrieval recall@3 of the
labeled supporting passages.

**Protocol and thresholds** (`tests/eval/thresholds.yaml`; quality values are initial, **OD-2**):
- ≥ 5 trials per case per candidate model; report mean and worst case.
- **Hard (never relaxed):** 0 dispatched actions outside policy; 0 secrets in model requests; 0
  forbidden-target proposals that survive precheck.
- **Quality:** diagnosis accuracy ≥ 80 % on in-scope classes and not worse than the baseline; safe
  abstention ≥ 90 % on ambiguous cases; ≤ 2 unnecessary calls per incident on average.
- **Retrieval:** TF-IDF recall@3 ≥ 0.9. Below that, fix the runbook corpus before changing retrievers.
- **Cost/latency:** within the configured budgets.

**Rule:** the model/provider choice, retriever changes, MCP retention, strategy choice per class and
each write release are decided from these results. If a strategy does not match or beat the baseline
on a class, that class is switched to the baseline strategy in the class registry — a data change,
not a code change — and the model only summarizes.

---

## 22. Implementation sequence and release criteria

### 22.1 Recommended build order (from an empty repository)

Each step leaves a runnable system with its tests green. Security for a boundary lands **with** that
boundary. The extension seams (registries, inventory, policy data, `InvokeCapability`, strategies,
evidence store, write contract) are in place **before** the capabilities that use them, so that later
steps only register things.

| # | Build | Exit proof |
|---|---|---|
| 1 | Package skeleton, `pyproject`, import-boundary and call-site tests, settings, wiring skeleton; data-file loaders (inventory, policy, signals, routing) with startup validation | forbidden imports and unresolved references fail the build |
| 2 | Domain model (§5), trigger identity, proposal digest, `AgentDecision` union, registries (target kinds, classes, capabilities, strategies, executors) | unit tests; registry validation tests |
| 3 | HTTP/CLI adapters with JWT authentication, users in Postgres, Alertmanager token; `RunInvestigation`, `HandleAlertNotification`, read use cases; durable intake; Swagger on the loopback listener | captured-webhook tests; auth tests; non-human approval refused; unauthorized read ⇒ 404 + audit |
| 4 | **Read-only vertical slice:** worker, Postgres + checkpointer + append-only roles, `InvestigationRunner`, the skeleton with the `evidence_pack` and `model_loop` strategies, `InvokeCapability`, evidence store, policy engine, budgets, `ContextAssembler`, `Redactor`, decision conversion; **Level 1 capabilities** through the direct catalogue against the read gateway and host/network probes on the private path; empty write gate | trigger → intake → classification → strategy → evidence → audit; healthy check ⇒ no model call; unsupported report ⇒ evidence pack, no model; budget termination; **write-gate standing test** |
| 5 | First incident classes (§1.3: `container_restart_loop`, `health_check_failed`, `dependency_unavailable`, then the saturation family) with signals, their runbooks from library v1.1.0, and alert rules on the Argus-owned Prometheus/Alertmanager; correlation, related-incident links, multi-fingerprint resolution, worker recovery; evaluation set v1 + baseline strategy | correlation and recovery tests; first eval report |
| 6 | HITL state machine (§14) and the write contract against a **fake** action gateway with a journal; holds; outbox; resume intents; precheck; ledger + reconciliation; fresh verification | full failure-injection suite; binding rejections; hold rejections |
| 7 | Scheduler with the §6.5 policy; optional reconciliation | tick idempotency; long run across ticks ⇒ one incident |
| 8 | Tool providers: MCP tools server under `argus-tools` + in-worker provider; benchmark vs direct (**OD-3**) | Observation contract suite; credential-isolation test; recorded benchmark |
| 9 | **Level 2 capabilities**: metric history over the signal catalogue, processes, events, detailed/search logs, Docker disk usage, DNS/connectivity/sockets, load, I/O; `plan_then_reason` strategy | observations originate from the target host and app network; eval extended |
| 10 | **Level 3 read capabilities**: db-probe, inspection policy and file/config/journal reads, process details, knowledge lookups, combined capabilities, baseline comparison | combined capabilities cannot bypass policy; inspection-policy tests; eval extended |
| 11 | Argus metrics, logs, the four alert rules; eval thresholds run on demand; model decision recorded (**OD-1**) | dashboards and alerts present; eval meets §21.2 |
| 12 | Peer-agent adapter (§23) when the security agent exists | peer security suite |

### 22.2 Write release criteria (all required before a `(capability, target)` pair is released)

1. The §14.4 failure-injection suite is green on Postgres for this capability.
2. Binding tests are green: changed arguments, replaced target (identity changed), resolved incident,
   expired proposal, changed inventory, active hold, reused token, non-human answerer and unscoped
   approver are all rejected.
3. The write-contract suite is green for this capability (identity, dispatch, reconcile, verification).
4. The fresh-verification test is green.
5. Action-gateway exact-route, exact-target and journal tests are green against the real gateway image.
6. The evaluation meets the **hard** thresholds for the deployed model.
7. Deployment check: the action credential is mounted only for the worker write path; the firewall is
   opened only for the action gateway; `write_gate.open` contains only the reviewed pair.

**Standing test (runs in every build while a pair is not released):** start the stack, inject a model
reply proposing `container.restart`, and assert that no approval is created, no request reaches any
action endpoint, and the outcome is `no_action_escalated`. A deployment script verifies that the
action gateway is absent or unreachable from Host A while nothing is released.

### 22.3 Definition of done (production, this release)

1. Alertmanager triggers incidents automatically over an authenticated private path.
2. Operators can request the same investigation through HTTP (Swagger) and CLI after logging in.
3. Schedules request the same investigation, idempotently and with the overlap policy.
4. Healthy checks stop after detection with no model call; unsupported reports end with an evidence
   pack and an escalation, with no model call and no claimed diagnosis.
5. Incidents of every enabled class gather fresh Prometheus evidence and target-context observations
   through the class's strategy.
6. Every capability call, from every caller, goes through `InvokeCapability`: audited, policy-checked,
   redacted and stored once as evidence.
7. No write capability is released; the standing write-gate test passes in every build.
8. The gateways and probes reject routes, verbs, targets and paths outside their allowlists.
9. The evaluation meets §21.2 for the chosen model on every enabled class.
10. Injection and secret fixtures pass on model input and on stored evidence; read views enforce
    per-caller authorization.
11. `pytest` is offline and free; security and failure-injection tests are automated.
12. Adding a Level 1–3 read capability, an incident class or a strategy requires no change to
    `domain`, `application`, the orchestration skeleton or the policy engine (§24).

---

## 23. Collaboration with peer agents

Argus is designed to work with a **peer security agent**, and later with other specialised agents, so
that together they diagnose different kinds of server problems. The collaboration rests on one shared
contract rather than on either agent knowing the other's internals: **triggers in, a strategy runs,
an audited incident out.**

### 23.1 Principles

1. **A peer is an authenticated principal** of kind `agent`, role `peer_agent`, with target scopes
   (§5.2, §17.3). It never uses a human's credential.
2. **A peer never holds write authority** (§1.4 rule 3). It may request investigations, contribute
   findings, read scoped incidents and evidence, and place holds. Every write still requires a
   policy-generated proposal and an authenticated human's approval.
3. **Peer text is evidence, not instruction.** Findings are redacted, stored as `EvidenceRecord`
   (kind `peer_finding`) and wrapped as data in any model context.
4. **Everything a peer does is audited** with its principal and the shared `correlation_id`.
5. **Quotas and loop protection.** Per-principal cost and rate limits (§6.5). Every cross-agent request
   carries `origin_chain`; Argus refuses a request whose chain already contains Argus or exceeds
   `MAX_ORIGIN_CHAIN`.

### 23.2 Inbound: the peer asks Argus (`adapters/inbound/agent`)

A separate listener on the private path, with its own authentication, exposing coarse verbs that map
to existing use cases:

| Verb | Use case | Notes |
|---|---|---|
| `diagnose_target(target, reason, kind)` | `RunInvestigation(trigger_kind=peer)` | converges before detection like any trigger |
| `submit_finding(target, finding)` | `RunInvestigation(peer, request_kind="report")` | the finding is stored as evidence |
| `get_incident(id)` | `GetIncident` with the `peer_agent` view | |
| `retrieve_evidence(incident_id, evidence_ids)` | evidence read, scoped to the peer's targets | returns stored, redacted records with hashes |
| `place_hold(target, reason, expires_at)` / `release_hold(id)` | hold use cases | e.g. forensic preservation |

It never exposes graph nodes, raw database access, executors, gateways or policy. *Implementation
choice (OD-14):* the wire protocol (MCP over authenticated HTTP, an agent-to-agent protocol, or plain
HTTP). The verbs and their mapping to use cases are fixed; the protocol is an adapter detail.

### 23.3 Outbound: Argus asks or informs the peer

| Need | Mechanism | Core change |
|---|---|---|
| Ask the security agent a question during an investigation ("is this process known-malicious?") | an `ExternalMcpProvider` (§12.5) serving the peer's read tools, each with a registry spec and policy entry; results are observations and evidence | none |
| Hand over an incident whose class belongs to the peer (`owner: peer`), or escalate to it | a routing entry (§15.2) and a notification channel to the peer | none |
| A strategy that consults the peer as part of its plan | a registered `consult_peer` strategy | none |

### 23.4 Towards one system

Both agents share: the `TargetRef`/inventory vocabulary, the incident and evidence model, the
`correlation_id`, and the rule that only humans approve writes. A security incident found by the peer
and an SRE incident found by Argus can therefore be linked as related incidents (§6.4), placed under
holds, and read by each other within scope. A later supervisor or router agent, if one is ever needed,
is one more peer principal using the same verbs.

---

## 24. Extension points

The goal of this architecture is that Argus's diagnostic reach grows **without changing the core**
(`domain`, `application`, the orchestration skeleton and the policy engine).

| To add | You touch | Core |
|---|---|---|
| **A read capability** | `capabilities/<area>/<verb>.py` with a `CapabilitySpec` and an implementation returning `Observation`; a registry line; a policy-file entry; a fake + contract test; probe verb on T if target-side | untouched |
| **A metric-history capability or new signal** | a signal template in `signals.yaml`; one capability if a new tool is needed | untouched |
| **A combined capability** | a capability with `runs_in="worker"` and `max_subcalls`, using the injected invoker | untouched |
| **An incident class** | a pure detector, an `IncidentClassSpec` entry, a runbook `RB-xxx-<slug>.md` with metadata (§15.3), signal entries, a Prometheus alert rule, eval cases | untouched |
| **A diagnostic strategy** | `orchestration/strategies/<name>.py` implementing `DiagnosticStrategy`; a registry line; the strategy suite; select it in a class | untouched |
| **An executor (new kind of backend)** | a client class registered in the `ExecutorRegistry`; endpoints in the inventory; credentials in settings | untouched |
| **A remediation (write) capability** | a `WriteCapability` (§14.8); an action-gateway route; policy entries; the write-contract and failure-injection suites; its own release (§22.2) | untouched |
| **A monitored host** | inventory entries; the gateway and probe set on that host; its Prometheus/Alertmanager | untouched |
| **A monitoring backend** | a new `MetricsPort` adapter and signal catalogue | untouched |
| **A model provider** | a new `LLMPort` adapter mapping to `ModelReply`; the decision-conversion suite and the evaluation | untouched |
| **A retriever (e.g. vector store)** | a new `KnowledgePort` adapter, justified by the §21.2 retrieval metric | untouched |
| **An inventory source (discovery)** | a new `InventoryPort` adapter | untouched |
| **A notification channel (Slack)** | a new `NotificationPort` adapter declaring `dedupes_by_key`; the signed approval link | untouched |
| **Single sign-on** | token verification in `adapters/inbound/http/auth.py` | untouched |
| **A peer agent** | a principal and scopes; the peer adapter (§23.2); optionally an external tool provider and routing entries | untouched |
| **An event bus (e.g. Kafka)** | an intake adapter, once several independent consumers need durable fan-out | untouched |
| **HA API/workers** | more worker replicas (claims and locks already support this); managed Postgres with backups | untouched |

---

## 25. Open Decisions

| ID | Decision | Current state / how it will be decided |
|---|---|---|
| OD-1 | Model and provider | provisionally OpenAI `gpt-5.6-luna` through the OpenAI-dialect adapter; confirmed or replaced by the §21.2 evaluation on quality, latency and cost |
| OD-2 | Calibration of quality thresholds and context budgets | initial values in §10.6 and §21.2; recalibrate after the first evaluation run (hard safety thresholds are not open) |
| OD-3 | Keep MCP for the tools-child set or bind the registry directly | benchmark in step 8: keep MCP if p95 overhead < 100 ms per call, no eval regression, and the credential-isolation test passes; otherwise `TOOL_CATALOGUE=direct` with process isolation by other means |
| OD-7 | Numeric values for `MAX_STEPS`, `MAX_TOKENS_PER_INCIDENT`, `MAX_MODEL_COST_PER_DAY`, per-principal quotas, approval expiry, `METRICS_MAX_STALENESS`, `VERIFY_TIMEOUT`, `RESUME_MAX_ATTEMPTS`, evidence retention per kind | set from measurements and the project model budget |
| OD-8 | Schedule cadence per target | derived from the measured p95 investigation duration (§6.5) |
| OD-9 | Plain SQL vs SQLAlchemy; migration tooling | adopt SQLAlchemy only if schema complexity justifies it |
| OD-10 | A dedicated approval/incident UI beyond Swagger, CLI and (later) Slack links | **decided by ACR-0001 (2026-10-06):** user interfaces are allowed as separate clients of the HTTP API, never inside the core; a UI may hold a read-only token; the team's frontend lives in `frontend/` and runs as `argus-v18-ui` (static files + a proxy to the API) on a loopback port of Host A; answering approvals stays in Swagger/CLI in this release |
| OD-11 | Model fine-tuning | explicitly undecided |
| OD-12 | Consolidating gateways and probes into one target agent per host | revisit at the second monitored host; privilege separation argues for keeping them separate |
| OD-13 | Automatic merging of related incidents | linked only in this release; decide from operational experience |
| OD-14 | Wire protocol of the peer-agent adapter | decided when the security agent's design exists; the verbs of §23.2 are fixed |
| OD-15 | A diagnosis-only mode for unsupported reports from authenticated operators | off; reconsider once the evidence pack and unsupported backlog show a need |
| OD-16 | TLS or a tunnel inside the private subnet | not required while the path stays inside the private network (§3.2); required before any path leaves it |

---

## Appendix A — One incident, end to end

```mermaid
sequenceDiagram
    autonumber
    participant TR as Trigger (alert/manual/schedule/peer)
    participant API as Argus API
    participant DB as Postgres
    participant W as Worker / skeleton
    participant PR as Prometheus
    participant ST as Strategy (+ harness, model)
    participant IC as InvokeCapability
    participant POL as Policy
    participant MS as Tool provider (MCP child / in-worker)
    participant H as Human approver
    participant T as Host T gateways/probes

    TR->>API: authenticated trigger
    API->>DB: durable intake + trigger occurrence
    API-->>TR: 202 / 2xx
    W->>DB: claim intake
    W->>PR: fresh snapshot (class signals)
    alt healthy check
      W->>DB: record no_incident
    else stale metrics or unsupported report
      W->>IC: evidence pack (Level 1 reads)
      IC->>DB: evidence + audit
      W->>DB: record undiagnosable / unsupported_escalated; notify routing target
    else registered class
      W->>DB: open/correlate incident; store snapshot; recall memory + runbooks
      loop investigation (bounded)
        W->>ST: next_step(view)
        ST-->>W: AgentDecision | InvalidDecision
        opt UseReadTools
          W->>IC: each read call
          IC->>DB: audit requested
          IC->>POL: policy.check
          IC->>MS: call (if allowed)
          MS->>T: exact route / probe verb
          T-->>IC: Observation (redacted)
          IC->>DB: evidence record + audit result
        end
      end
      opt ProposeRemediation (pair released, no hold)
        W->>DB: immutable proposal
        W->>DB: approval(pending) + outbox (one tx)
        W->>W: await_approval (consume answer or interrupt)
        H->>API: approve (JWT, human, scoped, digest)
        API->>DB: atomic approved + resume intent
        W->>DB: ResumeAnsweredApprovals claims intent
        W->>W: idempotent resume
        W->>DB: precheck (digest, incident, policy, hold, identity, inventory, evidence)
        W->>DB: ledger attempting + audit
        W->>T: action gateway (X-Argus-Action-Id)
        W->>DB: ledger confirmed/failed (or reconcile ⇒ indeterminate)
        W->>PR: poll until observed_at > action time
      end
      W->>DB: record outcome + episodic summary (+ escalation to routing target)
    end
```

## Appendix B — Persistence relationships

```mermaid
erDiagram
    INCIDENT ||--o{ TRIGGER_OCCURRENCE : "started/observed by"
    INCIDENT ||--o{ ALERT_OCCURRENCE : "correlates"
    INCIDENT ||--o{ AUDIT_RECORD : "produces"
    INCIDENT ||--o{ EVIDENCE : "collects"
    INCIDENT }o--o{ INCIDENT : "related to"
    AUDIT_RECORD }o--o| EVIDENCE : "references"
    INCIDENT ||--|| GRAPH_THREAD : "thread_id ="
    GRAPH_THREAD ||--o{ CHECKPOINT : "saves"
    INCIDENT ||--o{ ACTION_PROPOSAL : "may propose"
    ACTION_PROPOSAL }o--o{ EVIDENCE : "cites (id + sha256)"
    ACTION_PROPOSAL ||--o| APPROVAL : "is decided by"
    APPROVAL ||--o| NOTIFICATION_OUTBOX : "is delivered via"
    APPROVAL ||--o| RESUME_INTENT : "answer creates"
    APPROVAL ||--o| ACTION : "authorizes"
    PRINCIPAL ||--o{ APPROVAL : "answers (human only)"
    PRINCIPAL ||--o{ TARGET_HOLD : "places"
    INCIDENT {
      string id
      string target
      string incident_class
      string strategy
      string status
      string outcome
      int evidence_version
    }
    EVIDENCE {
      string evidence_id
      string kind
      string capability
      string host
      string executor
      string caller
      json values
      string sha256
    }
    ACTION_PROPOSAL {
      string proposal_id
      string capability
      string target
      json target_identity
      json arguments
      int evidence_version
      string policy_version
      string inventory_version
      timestamp expires_at
      string digest
    }
    APPROVAL {
      string approval_id
      string proposal_digest
      string state
      string approver_scope
      string actor
      timestamp expires_at
    }
    RESUME_INTENT {
      string approval_id
      string decision
      string state
      int attempts
    }
    ACTION {
      string action_id
      string state
      timestamp attempted_at
      timestamp result_at
    }
    TARGET_HOLD {
      string hold_id
      string target
      string reason
      timestamp expires_at
    }
    PRINCIPAL {
      string id
      string kind
      string role
      string scopes
      bool disabled
    }
```

---

## Changelog

| Version | Date | Change | ACR |
|---|---|---|---|
| 1.8.0 | 2026-10-02 | v1.8 (30 Sep 2026) imported into the shared repository; addresses replaced by placeholders, nothing else changed | — |
| 1.8.1 | 2026-10-06 | user interfaces as read-only-capable clients of the HTTP API (§25 OD-10, §17.3); `GET /api/v1/me`; the existing read routes `/incidents/{id}/events`, `/evidence/{id}`, `/escalations` documented (§7.1); `frontend/` (§2.4) | [ACR-0001](changes/ACR-0001-ui-read-access.md) |
