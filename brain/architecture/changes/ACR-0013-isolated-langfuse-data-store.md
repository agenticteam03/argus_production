# ACR-0013 - Isolated Langfuse data store on the Argus host

| Field | Value |
|---|---|
| Status | `proposed` - this PR records the decision for review; no architecture text or deployment is applied yet |
| Proposed by | conantkd (+ agent) - 2026-10-14 |
| Accepted by | pending review |
| Second approval (safety principle only) | not required: the existing host boundary, secrets rules, read-only rule and audit separation remain unchanged |
| Architecture version | current `1.8.10` to the next free version when applied (tentatively `1.8.12`; ACR-0012 proposes `1.8.11`) |
| Task / PR | [LF-2](../../tasks/current/LF-2-langfuse-db-architecture.md) - PR to be assigned |

## 1. Detect and explain

The team selected self-hosted Langfuse on Host A (vm-095) for optional agent tracing. Host A already runs Argus PostgreSQL 16, so two database arrangements are possible. The decision is to **start with a separate PostgreSQL service and data volume for Langfuse**, keeping the existing Argus database server and credentials untouched. Sharing the Argus PostgreSQL server remains a measured fallback if the separate service's resource cost prevents an otherwise viable same-VM deployment.

The LF-1 synthetic trial is evidence about startup, not a production capacity pass. On the one-CPU, 5900-MiB host, the isolated six-service stack reached readiness in 256 seconds with 3584 MiB of combined container limits and accepted one OTLP batch of 10 traces. A concurrent recreation of Argus containers stopped the trial before the planned 60-trace / 120-observation read check. The previous smaller Node heaps caused worker or web exits. The full coexistence result remains unknown. The trial used its own PostgreSQL and was removed after execution. See the [LF-1 task and evidence at its pushed checkpoint](https://github.com/agenticteam03/argus_production/blob/a6cc843/brain/tasks/current/LF-1-langfuse-capacity.md) and [interrupted run](https://github.com/agenticteam03/argus_production/blob/a6cc843/brain/execution/history/LF-1/step-09/evidence.md).

The [Langfuse self-hosting PostgreSQL specification](https://langfuse.com/self-hosting/deployment/infrastructure/postgres) recommends PostgreSQL 16 for v4 and uses the `public` schema of its selected database. The existing Argus server is version 16, but its current configuration is limited to 256 MiB and 30 connections. Compatibility alone does not establish safe shared capacity.

## 2. Why the current architecture is insufficient

- Section 3.1 places only the Argus API, worker, scheduler and `postgres` on Host A. It does not place Langfuse or describe the resource boundary between its data store and Argus state.
- Section 3.5 says `postgres` holds "all Argus durable state". It gives no separate ownership rule for Langfuse data and does not define the allowed fallback.
- Section 18.5 allows optional Langfuse/OpenTelemetry tracing but does not say where self-hosted Langfuse runs or which data services it needs. Section 18.1 already requires telemetry failure to leave investigations running and forbids treating traces as audit records; this proposal keeps both rules.

Without an explicit topology and decision gate, a deployment could silently point Langfuse migrations at the Argus database or overload its 30-connection server. The current architecture cannot distinguish a validated fallback from an accidental shared dependency.

## 3. Smallest reasonable change

When this ACR is accepted and the first deployment work is ready, amend sections 3.1, 3.2, 3.5 and 18.5 in the same implementation PR. The proposed text is:

> On Host A, optional self-hosted Langfuse consists of web, worker, an independently provisioned PostgreSQL service and named volume, ClickHouse, Redis/Valkey and S3-compatible object storage. Each service has explicit CPU/memory limits and a private Host-A network path; no Langfuse service is published to the Internet by this decision. The initial configuration uses a dedicated Langfuse database, database login, credentials, migrations, volume and backup scope. Langfuse may not connect with an Argus database login or migrate an Argus database.
>
> If an isolated trial shows that the separate PostgreSQL service is the limiting resource, the team may instead use the existing Argus PostgreSQL server. This requires a **different database and non-superuser login** dedicated to Langfuse, an explicit combined connection/memory/CPU budget, independent backup/restore procedures at database level, and a repeated acceptance run with both workloads. Sharing a server is not an automatic fallback when a readiness check fails. If the bottleneck is ClickHouse, the application containers or the single CPU, consolidating PostgreSQL is not considered a remedy. No production configuration changes until the selected topology passes the gate below.
>
> The acceptance run verifies Langfuse startup, 60 synthetic traces and 120 observations submitted through native OTLP and retrievable through the v2 read API, no Argus container recreation/OOM, continuous Argus health, at least 900 MiB available throughout, and NO INTERFERENCE. It must run without concurrent Argus deployments. Retention, backup/restore, secret injection and normal workload monitoring are specified before a permanent deployment. Langfuse ingest failure does not block Argus investigations or audit, and tracing must not ingest unredacted secrets.

Section 3.1 gains Langfuse as an **optional colocated telemetry stack** on Host A. Section 3.2 gains a private local network for the stack. Section 3.5 gains its six services, with the standalone PostgreSQL as the default and a separate-database Argus-server fallback. Section 18.5 refers to the deployment and acceptance gate. The architecture version and changelog are updated only when the design is applied.

**Alternatives considered**:

- Share Argus PostgreSQL immediately. This saves one process/volume but couples connection, memory, migration timing and outage risk before combined capacity is measured; keep it as the measured fallback above.
- Move Langfuse to another VM or a managed service. This adds infrastructure outside the team's selected same-VM deployment.
- Keep the present optional tracing paragraph and choose the data store in Compose. This leaves the database ownership and fallback decision out of the architecture and makes the implementation hard to review.

## 4. Consequences

- **Code and deployment:** a later PR adds pinned images, bounded resources, secrets, isolated storage and OTLP instrumentation; it never makes tracing a required Argus application port. The LF-1 experiment is evidence and a harness, not a deployment specification.
- **Tests:** repeat the bounded LF-1 trial in a quiet VM window; include both Argus and Langfuse health, ingestion/read verification, and backup/restore checks before promotion. Repeat the same acceptance gate if the shared-server fallback is chosen.
- **Risk:** both PostgreSQL services still share Host A CPU, RAM and disk. Separate containers and volumes reduce database-level coupling but do not provide host fault isolation. A shared-server fallback increases blast radius and requires a capacity review.
- **Reversal:** disable the optional telemetry exporter, stop the dedicated Langfuse stack, and retain its data for the configured retention/backup period. A shared-server fallback is reversed by exporting and restoring only the Langfuse database into a dedicated service; Argus schemas and credentials remain untouched.
- **Safety principle:** no change to read-only, write gate, host isolation from monitored targets, evidence integrity, secrets policy or audit separation. The implementation must preserve all of them.

## 5. Decision

**Proposed for team review:** use a separate PostgreSQL service for Langfuse on Host A. Permit the existing Argus PostgreSQL server only as the measured, separately permissioned fallback specified in section 3. Acceptance and implementation remain pending; no production database or tracing configuration is changed by this ACR PR.

## 6. Applied

- [ ] A teammate accepts this ACR in its PR.
- [ ] `ARCHITECTURE.md` sections, version and changelog updated in the first implementation PR.
- [ ] The first permanent code/deployment change and accepted architecture update are reviewed together.
- [ ] A stable full-capacity acceptance run passes for the chosen database arrangement.
