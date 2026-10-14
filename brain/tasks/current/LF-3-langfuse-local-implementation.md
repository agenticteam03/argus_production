# LF-3 — Local Langfuse integration and Agent observability view

Status: local implementation; VM validation pending a lease. No pull request or push is authorized for this task.

Scope: the worker tracing is `argus/observability/tracing.py` (ACR-0013 A/B/C; bounded async exporter, spans as nodes close; the earlier synchronous `langfuse.py` draft was dropped). Add metadata-only OTLP/HTTP tracing to the investigation runner, a private Langfuse v4 Compose stack on vm-095,
and a read-only observability view in the existing Agent route. Preserve audit and investigation outcomes if telemetry
fails. Keep Langfuse project keys in the worker only. The default Langfuse PostgreSQL is separate from Argus PostgreSQL.

Acceptance: focused backend and frontend tests, full local suites, frontend build/lint, Compose validation, local UI
preview, then VM canary, ingestion, privacy and resource checks after the lease. See `deploy/langfuse/README.md` for
the VM sequence. No VM state is changed by this branch.
