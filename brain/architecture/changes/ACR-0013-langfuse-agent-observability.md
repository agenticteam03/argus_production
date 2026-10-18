# ACR-0013 - Self-hosted Langfuse for Argus agent observability

| Field | Value |
|---|---|
| Status | `accepted` - its host changed by [ACR-0016](ACR-0016-langfuse-cloud.md) (Langfuse Cloud instead of Host A) |
| Proposed by | conantkd (+ agent) - 2026-10-14 |
| Accepted by | juanbetancurm - PR #156 review, 2026-10-16 |
| Second approval (safety principle only) | not required for this proposal: read-only, audit, secrets and target-host isolation rules are preserved |
| Architecture version | applied at `1.8.16` together with ACR-0016 |
| Task / PR | [LF-2](../../tasks/current/LF-2-langfuse-db-architecture.md) - PR #150 |

## 1. Detect and explain

The team wants to see how the Argus agent investigated an incident: graph nodes, model calls, tool calls, timing, errors and token use. Section 18.5 permits optional Langfuse/OpenTelemetry tracing but does not define an integration. The team selected self-hosted Langfuse on Host A (vm-095), where Argus runs; there is no third VM. The initial database choice is a **separate PostgreSQL service for Langfuse**. The existing Argus PostgreSQL 16 server remains a measured fallback if the separate service itself is the limiting resource.

**Observed LF-1 result:** on the one-CPU, 5900-MiB Host A, an isolated six-service stack reached readiness in 256 seconds under 3584 MiB of combined container limits and accepted one native OTLP batch (10 synthetic traces). Smaller Node heaps caused worker/web exits. A concurrent Argus container recreation interrupted the planned 60-trace / 120-observation read check. This is evidence of startup and one accepted batch, **not** of sustained coexistence or production capacity. The trial stack and volumes were removed. See the [pushed LF-1 task](https://github.com/agenticteam03/argus_production/blob/a6cc843/brain/tasks/current/LF-1-langfuse-capacity.md) and [interrupted run](https://github.com/agenticteam03/argus_production/blob/a6cc843/brain/execution/history/LF-1/step-09/evidence.md).

**Documented compatibility:** [Langfuse v4](https://langfuse.com/self-hosting/deployment/infrastructure/postgres) recommends PostgreSQL 16 and uses the `public` schema in the selected database. Argus's PostgreSQL 16 is configured with 256 MiB and 30 connections; version compatibility does not prove safe sharing. Native OTLP ingestion uses `/api/public/otel/v1/traces` with `x-langfuse-ingestion-version: 4`; the v4 read path is [Observations API v2](https://langfuse.com/docs/api-and-data-platform/features/public-api).

## 2. Why the current architecture is insufficient

- Sections 3.1, 3.2 and 3.5 list the Host-A services and networks but no Langfuse services, data stores, private telemetry path or resource boundaries.
- Section 8.2 and section 18.5 call tracing optional infrastructure, but do not define how the actual LangGraph runner, model adapter and `InvokeCapability` publish correlated spans. Current `argus/observability/run_events.py` is an event contract, not a Langfuse exporter; wiring currently passes the existing store as the runner's event sink.
- Section 18.1 makes audit mandatory and telemetry optional. The integration must explicitly preserve this distinction; otherwise export errors could become investigation failures or a trace could be mistaken for audit evidence.
- Section 17.2 governs credentials and section 16 governs Argus durable state. Neither authorizes Langfuse migrations against the Argus database, raw evidence export or a public Langfuse listener.

A deployment selected only in Compose would silently decide these cross-cutting boundaries without an architectural record.

## 3. Smallest reasonable change

When accepted, update sections 3.1, 3.2, 3.5, 17.2 and 18.5 (and the communication matrix in section 3.3) in the first implementation PR. The contract to add is below.

### 3.1 Infrastructure and connections

```text
Host A (agent VM)
  argus-v18-worker (LangGraph runner, LLM adapter, InvokeCapability)
       | optional, bounded OTLP/HTTP; private network; Langfuse project key
       v
  Langfuse web/API ---> Langfuse PostgreSQL (users, projects, keys, settings)
       |       |------> Redis/Valkey (queue/cache)
       |       |------> S3-compatible MinIO (event/media objects)
       |       `------> ClickHouse (trace reads)
       v
  Langfuse worker ---> Redis/Valkey, S3, ClickHouse and Langfuse PostgreSQL

  Argus API / audit / checkpoint store ---> Argus PostgreSQL (unchanged)
```

| Source | Destination | Purpose and protocol | Credential / exposure |
|---|---|---|---|
| Argus worker | Langfuse web/API | `POST /api/public/otel/v1/traces` over private OTLP/HTTP; v4 ingestion header | dedicated Langfuse project key pair; internal only |
| Langfuse web and worker | Langfuse PostgreSQL | application state and migrations | dedicated Langfuse DB login; internal only |
| Langfuse web and worker | ClickHouse | trace storage/query | dedicated ClickHouse login; internal only |
| Langfuse web and worker | Redis/Valkey | queue/cache | dedicated credential; internal only |
| Langfuse web and worker | MinIO | S3-compatible event/media objects | dedicated access key; internal only |
| Operator | Langfuse web UI | investigation of telemetry | own login, initially Host-A loopback only |
| Argus API, scheduler, frontend and Host T | Langfuse | no integration connection | no Langfuse credential |

Six Langfuse services run on Host A: web/API, worker, PostgreSQL, ClickHouse, Redis/Valkey and S3-compatible MinIO. Use pinned, Host-A-compatible images, persistent named volumes for stateful services, explicit CPU/memory limits, startup health checks, retention and backup/restore procedures. The web/API receives OTLP on a private Docker network; no Langfuse port is exposed publicly or proxied through the Argus public UI by this ACR. An operator-only Langfuse UI may initially bind to Host-A loopback with its own authentication; any public access requires a separate reviewed edge design. No Host-T component connects to Langfuse.

The core tracing path does **not** require a Langfuse-owned LLM or an LLM API key. Argus continues calling its configured model through `LLMPort`; Langfuse receives metadata about those calls after the fact. The initial deployment leaves Langfuse AI/provider settings unset and disables its in-app Assistant (`LANGFUSE_IN_APP_AGENT_ENABLED=false`). Playground, LLM-as-a-Judge and prompt experiments are outside this deployment; enabling them later requires a separate provider, key, egress and cost decision. See the [Langfuse LLM API/Gateway specification](https://langfuse.com/self-hosting/deployment/infrastructure/llm-api).

Only the Argus **worker** receives the Langfuse project keys and internal OTLP endpoint. The frontend, target tools process, scheduler and API do not receive these credentials. Langfuse-to-Argus API, Argus database and audit-sink connections are absent. Argus does not read Langfuse to diagnose an incident; its evidence and audit remain in Argus storage. The exporter is asynchronous and bounded so the graph never waits indefinitely for Langfuse. Network failure, queue saturation or Langfuse downtime drop telemetry and increment a local failure metric; they do not fail an investigation or bypass the mandatory audit write.

### 3.2 Trace contract

One Argus investigation **execution attempt** becomes one root trace. Its attributes include `incident_id`, incident class, strategy, outcome and an attempt identifier. A resumed attempt makes a new root trace with the same `incident_id`; tracing context is not added to checkpointed graph state. Child spans cover graph nodes (`detect`, `recall`, `investigate`, `act`, `record` and the evidence-pack path), model requests through `LLMPort`, and read calls through `InvokeCapability`. The context is carried within the worker so nested spans share the root. This is optional instrumentation at the infrastructure boundary, never a new application port or an alternate tool-execution path.

Export a small allowlist: operation/node name, capability name, status/error category, durations, model identifier, token counts and estimated cost when known, and opaque evidence IDs for correlation. Do not export raw prompts, model replies, tool arguments/results, evidence bodies, secrets, credentials, target addresses or approval payloads by default. Any later content capture requires a separate redaction, access and retention review. Use manual, filtered OTLP spans; avoid SDK auto-instrumentation that may capture request or response bodies. Trace export never writes Argus audit records or influences budgets, policy decisions or diagnoses.

The integration is disabled by default in wiring (`tracing_noop.py`); enabling it selects an OTLP exporter for the worker. It must support bounded buffering, batch export and shutdown flush with a short timeout. The separate dashboard presents telemetry only. Argus's existing run events, Prometheus metrics, logs, evidence store and audit remain authoritative for their respective purposes.

### 3.3 Database choice and fallback

The starting deployment gives Langfuse its **own PostgreSQL service, database, non-superuser login, credentials, migrations, named volume and backup scope**. It must not connect with an Argus database login or migrate Argus's database. ClickHouse remains necessary for traces; Redis/Valkey and S3 remain necessary for the Langfuse data path. Separate PostgreSQL containers still share Host-A CPU, RAM and disk.

If a quiet, bounded acceptance run shows that this additional PostgreSQL process is the bottleneck, the team may evaluate the existing Argus PostgreSQL server as an alternative. Reuse means a **separate `langfuse` database and dedicated non-superuser login**, never Argus's database/schema/login. Before switching, record the combined connection, CPU, memory, disk and backup budgets, preserve Argus headroom, and repeat the acceptance run with both workloads. A failure caused by ClickHouse, web/worker limits or the single CPU is not solved by moving the database. There is no automatic fallback at runtime. If neither arrangement passes, defer the permanent deployment.

### 3.4 Acceptance and operation

A quiet-VM acceptance run must prove: all selected dependencies healthy (six services with dedicated PostgreSQL, or five Langfuse containers plus the existing PostgreSQL server in fallback mode); 60 synthetic traces / 120 observations accepted through native OTLP and retrievable through Observations API v2; no Argus container recreation, OOM or failed `/healthz` sample; at least 900 MiB available throughout; and `NO INTERFERENCE`. It must include representative Argus investigation activity in a later integration test, telemetry-disabled and telemetry-unavailable cases, and a check that audit/evidence still persist while export fails. Set retention, backup/restore, secret rotation, disk/queue alerts and Langfuse health monitoring before a permanent deployment. The isolated LF-1 run has not satisfied this gate.

**Alternatives considered:**

- Share Argus PostgreSQL immediately. Saves one process but couples resources and outage risk before combined capacity is measured. Retained only as the gated fallback above.
- Deploy Langfuse to another VM or managed cloud service. Adds infrastructure outside the team's same-VM constraint.
- Use automatic model/HTTP instrumentation with full input/output capture. Reduces adapter work but can export sensitive prompts or evidence; use explicitly filtered spans.
- Keep section 18.5's optional statement and choose everything in Compose. Leaves data ownership, credentials and failure behaviour undefined for reviewers.

## 4. Consequences

- **Code:** later work adds a filtered worker exporter at `argus/observability/`, wiring/settings, graph/model/capability span hooks and local drop/failure metrics; no change to the audit port or capability authorization path.
- **Deployment:** later work adds six bounded Langfuse services on Host A, secrets, private networking, volumes, backup/restore and alerts. The ACR PR itself deploys nothing. The accepted `ARCHITECTURE.md` update, version/changelog and first permanent code belong together in the implementation PR.
- **Tests:** exercise span correlation, omitted sensitive fields, fail-open telemetry with fail-closed audit, resume grouping, queue bounds, native ingestion/readback, Argus latency/health and teardown. The LF-1 full-capacity gate remains open.
- **Risk:** the same VM creates resource contention even with an isolated database. Monitoring, hard limits and a rollback path are required before enabling the exporter. The shared-PostgreSQL fallback increases coupling.
- **Reversal:** turn off the optional exporter, stop Langfuse and retain/restore its data under the chosen retention policy. No Argus checkpoint or audit migration is involved.
- **Safety principle:** no change to read-only, write gate, target-host isolation, evidence integrity, secrets policy or audit separation. Implementation tests must demonstrate these existing invariants.

## 5. Decision

**Proposed for team review:** integrate self-hosted Langfuse as optional, filtered OTLP observability of the Argus worker on Host A. Start with a dedicated Langfuse PostgreSQL service. Permit an explicitly tested separate-database arrangement on the existing Argus PostgreSQL server only when measured resource use supports it. Preserve Argus audit/evidence and investigation progress when telemetry is unavailable. Production enablement awaits the acceptance gate.

## 6. Applied

- [ ] Teammate accepts ACR-0013 in PR #150.
- [ ] First implementation PR updates `ARCHITECTURE.md` sections/version/changelog and adds the initial code/deployment together.
- [ ] A quiet-VM capacity run and a real Argus instrumentation/failure-injection run pass for the selected database arrangement.
