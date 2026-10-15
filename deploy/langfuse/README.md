# Langfuse observability on vm-095

> **2026-10-15 (LF-3 step 02):** this stack failed its capacity gate on vm-095 (1 vCPU, no swap): a ClickHouse merge
> was OOM-killed at its 768 MiB limit and the shared disk saturated (I/O pressure 99 %). It is stopped there.
> [ACR-0016](../../brain/architecture/changes/ACR-0016-langfuse-cloud.md) proposes Langfuse Cloud (EU) instead: set
> `ARGUS_TRACING_ENDPOINT=https://cloud.langfuse.com/api/public/otel/v1/traces` in `hosts.env` and put the Cloud
> project's keys in the same worker-only files. Keep this directory for a host with headroom.

This directory prepares a private Langfuse v4 deployment next to Argus. It is not deployed by this branch. The six
dedicated services use their own PostgreSQL database and volumes: web, worker, PostgreSQL, ClickHouse, Redis and MinIO.
The web UI listens only on `127.0.0.1:18300`; the Argus worker reaches it over `argus-v18-core`. No browser receives a
Langfuse project key. The existing Argus PostgreSQL remains untouched; using it later is a measured fallback, not the
default.

## Before VM execution

Confirm ACR-0013 has been accepted before deployment. Obtain the vm-095 and vm-166 leases required by the Argus Brain
protocol and confirm no concurrent deployment. Use
`brain/execution/current/code.bash` for every VM command. Check `/opt/argus-v18/DEPLOYED`, `deploy.sh status`,
`nonint-check.sh`, memory headroom and free disk before changing anything. The LF-1 trial accepted a 10-trace OTLP batch,
but its full capacity acceptance was interrupted by a concurrent core recreation; it does not prove production capacity.

Stage this `compose.yml` under `/opt/argus-v18/app/deploy/langfuse/`. Create a root-readable
`/opt/argus-v18/secrets/langfuse/runtime.env` with mode 0600 and these random, independently generated values:
`LF_POSTGRES_PASSWORD`, `LF_CLICKHOUSE_PASSWORD`, `LF_REDIS_PASSWORD`, `LF_MINIO_USER`, `LF_MINIO_PASSWORD`,
`LF_SALT`, `LF_ENCRYPTION_KEY` (64 hexadecimal characters), and `LF_NEXTAUTH_SECRET`. Generate values directly on the VM,
never in the repository or chat. Alphanumeric/hexadecimal credentials avoid URL escaping in `DATABASE_URL`. Start with
`docker compose --env-file /opt/argus-v18/secrets/langfuse/runtime.env -f /opt/argus-v18/app/deploy/langfuse/compose.yml up -d`.
Do not print `docker compose config` or `docker inspect` output: both can contain credentials.
Pin the image digests after the VM canary succeeds and before treating the stack as a reproducible deployment.

Reach the Langfuse UI through an SSH local port forward to `127.0.0.1:18300`, create the initial account/project, and
write its public and secret project keys into the worker-only mounted agent secret directory as
`langfuse_public_key` and `langfuse_secret_key` (mode 0600). Do not copy keys into the API, frontend, logs or command
history. Set `ARGUS_TRACING_ENABLED=1` in the Argus core Compose environment (the endpoint defaults to
`http://argus-v18-langfuse-web:3000/api/public/otel/v1/traces`) and recreate only `argus-v18-worker` after the
Langfuse health check passes. Tracing is off by default and also needs the two key files, so only the worker traces.
Spans are exported as each node closes, by a background thread with a bounded queue: a full queue or an unreachable
Langfuse drops telemetry (counted, logged once) and never delays or changes an investigation, its audit or its
records. Optionally set `ARGUS_LANGFUSE_UI_URL` and `ARGUS_LANGFUSE_PROJECT_ID` so the incident view links to the trace.

## Acceptance with the lease

1. Run Argus and lab baseline checks before and after each mutating step; stop if `nonint-check.sh` is not clean.
2. Confirm the six Langfuse services are healthy/running and `http://127.0.0.1:18300/api/public/health` responds.
3. Trigger one synthetic investigation through an approved Argus intake path. Note the `trace_id` in its run events
   (Agent page → selected run, or the incident's "Open in Langfuse" link) and verify that exact ID appears in the private Langfuse UI with a root agent observation,
   node spans, model generation when a model was called, and tool observations when tools ran.
4. Inspect the trace: no prompts, replies, evidence body, target names, host names, credentials or raw tool results may
   appear. Verify token counts and duration on any model generation.
5. Disconnect Langfuse temporarily without touching Argus data, trigger a synthetic investigation and confirm the
   incident still records and audits correctly. Restore Langfuse and repeat health checks.
6. Measure Argus API latency, worker run duration, memory pressure, swap and disk against the pre-change baseline.
   If the capacity budget is insufficient, disable `ARGUS_TRACING_ENABLED` and stop the Langfuse stack; preserve volumes
   for diagnosis. Do not migrate to the Argus PostgreSQL without a separate measured decision.

The Agent page uses Argus's existing read-only incident and run-event endpoints. A visible trace ID confirms local
instrumentation, not successful ingestion; Langfuse itself remains private. This separation avoids publishing a
Langfuse login or API proxy through the public Argus UI edge.
