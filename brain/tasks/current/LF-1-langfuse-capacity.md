# LF-1 - Langfuse capacity trial on the existing Argus VM

Status: startup verified and one native OTLP batch accepted; full capacity verification interrupted by concurrent core recreation. Owner: conantkd. VM: vm-095.

## Goal
Measure whether current Langfuse can coexist with Argus on vm-095 (one CPU, 5900 MiB RAM) under a small synthetic workload. This is not a production integration and does not export real Argus data.

## Scope and expected result
- Six temporary argus-lab-lf1 containers, five dedicated synthetic volumes, existing argus-v18-core network, no published ports.
- Independent Postgres, ClickHouse, Redis and MinIO; no credentials, databases or mounts from Argus.
- Total configured container RAM limit 3584 MiB; CPU quotas sum 0.73 CPU. Initial available RAM must be at least 4000 MiB.
- Abort below 900 MiB available, three consecutive API health failures, an existing Argus service changing/restarting, or the 20-minute trial deadline.
- Headless synthetic project; 60 synthetic traces with two OTLP observations each submitted and verified through the read API. No real model call.
- Monitor Argus /healthz and available RAM before, during and after. Record Docker stats, core restart/OOM state, and immutable image digests.
- A 25-minute independent watchdog cleans up a stalled trial. Normal cleanup removes only the dedicated Compose project and its five new volumes; pulled image caches are retained.
- PASS requires readiness, all traces retrievable, no core state change, no memory guard breach, clean teardown and NO INTERFERENCE.

## Commands and evidence
Commands are archived in brain/execution/history/LF-1/. The infrastructure expected results above replace a red test. No agent rebuild/deploy, persistent tracing configuration, public exposure, ACR application or production data migration is authorized by this trial.

## Limits
API health latency measures responsiveness, not diagnosis quality or representative simultaneous investigation load. A short synthetic test does not establish long-term retention, sustained ingestion or production capacity. The installed tracing backend would require an accepted architecture/deployment record, resource and retention policy, and a separate integration PR.
## Execution and compatibility findings

The first marker mismatch stopped the trial without VM mutation. The user then explicitly authorized sharing conantkd's existing AFTER-MERGE-main lease. Its marker was preserved; this task must not release or hand off that other task's lease. A fresh baseline explains the concurrent deployment change.

Worker/web V8 heap failures were observed under the initial limits. Final trial caps use worker 768 MiB / heap 512 MiB and web 1536 MiB / heap 1024 MiB. Readiness was observed with these limits. The first ingestion client used deprecated batch ingestion; v4 rejects trace/span writes in events_only mode. The updated harness uses native OTLP with x-langfuse-ingestion-version: 4 and cursor-based Observations API v2, bounded by start/end timestamps.

## PostgreSQL reuse proposal (not deployed)

The existing Argus PostgreSQL 16 is compatible with Langfuse v4 (minimum PostgreSQL 15; 16 recommended). Reuse the server with a dedicated langfuse database and a dedicated non-superuser owner/login; do not reuse the Argus database, schema or login. Langfuse manages its own public schema/migrations in its database. This avoids a separate PostgreSQL container but does not remove ClickHouse, Redis or S3 requirements.

Argus currently configures PostgreSQL at 256 MiB and 30 connections. Budget web/worker pools and Argus connections explicitly, then test migrations and concurrent ingestion before sharing. Separate databases do not isolate CPU, memory, connections, backups or server failure. No production database changes were made in this trial.

Sources: [PostgreSQL requirements](https://langfuse.com/self-hosting/deployment/infrastructure/postgres), [native OTLP](https://langfuse.com/docs/observability/get-started), [v4 read API](https://langfuse.com/docs/api-and-data-platform/features/public-api).

## Latest observed result

Step 09 reached readiness in 256 seconds and accepted 10 synthetic traces / 20 observations. The monitor then detected recreated Argus agent/worker containers and stopped before the full 60-trace read verification. Two Argus non-200 health samples occurred during startup. The cause of core recreation is not independently attributed; this harness does not recreate core services. This is an invalid coexistence measurement, not a Langfuse capacity pass or a proven Langfuse-induced failure.

Dedicated containers/volumes were fully removed; Argus /healthz is 200 and NO INTERFERENCE passed. No production PostgreSQL changes or persistent tracing were deployed. A stable test window is required for the full acceptance run. Do not release the other task's shared lease.
