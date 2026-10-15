# LF-3 — Local Langfuse integration and Agent observability view

Status: code merged (#152). Step 02 (2026-10-14/15): vm-095 on `main` `5d4b347`; the self-hosted stack failed the
capacity gate (a ClickHouse merge OOM-killed at its 768 MiB limit, the host's disk saturated, I/O pressure 99 %) and was
stopped, tracing rolled back ([evidence](../../execution/history/LF-3/step-02/evidence.md)). Proposed next:
Langfuse Cloud (EU), [ACR-0015](../../architecture/changes/ACR-0015-langfuse-cloud.md); step 03 enables it on vm-095
once accepted.

Scope: the worker tracing is `argus/observability/tracing.py` (ACR-0013 A/B/C; bounded async exporter, spans as nodes close; the earlier synchronous `langfuse.py` draft was dropped). Add metadata-only OTLP/HTTP tracing to the investigation runner, a private Langfuse v4 Compose stack on vm-095,
and a read-only observability view in the existing Agent route. Preserve audit and investigation outcomes if telemetry
fails. Keep Langfuse project keys in the worker only. The default Langfuse PostgreSQL is separate from Argus PostgreSQL.

Acceptance: focused backend and frontend tests, full local suites, frontend build/lint, Compose validation, local UI
preview, then VM canary, ingestion, privacy and resource checks after the lease. See `deploy/langfuse/README.md` for
the VM sequence. No VM state is changed by this branch.
