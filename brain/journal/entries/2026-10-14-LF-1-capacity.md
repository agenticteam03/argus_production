## 2026-10-14 - LF-1: same-VM Langfuse capacity findings and PostgreSQL reuse proposal

Type: infrastructure experiment
Who: conantkd (+ agent)
Context: the user explicitly authorized sharing the existing AFTER-MERGE-main lease. This task preserved its marker and did not release or hand it off.
Decision / result: Langfuse v4 starts on vm-095 with all six isolated services under 3584 MiB / 0.73 CPU total quotas. Worker/web require explicit V8 heaps (512/1024 MiB respectively) with 768/1536 MiB container caps; smaller heaps exited with code 134. The legacy test client was replaced with native OTLP and Observations API v2. A 10-second cold-request timeout was observed; a 60-second retry accepted one batch of 10 synthetic traces. The full 60-trace ingestion/read test was interrupted when existing Argus agent/worker containers were recreated concurrently. No full coexistence pass is claimed.

All trial containers and five dedicated synthetic volumes were removed after every run. Argus remains healthy; protected-object checks passed. No production database, credentials, public port or agent tracing configuration changed. The shared lease remains with the other task. PostgreSQL 16 can be reused with a separate Langfuse database/login, subject to explicit pool/resource budgeting and a later combined-load test; the existing Argus settings are 256 MiB and 30 connections. ClickHouse, Redis and S3 are still required.
References: [task](../../tasks/current/LF-1-langfuse-capacity.md), [latest evidence](../../execution/history/LF-1/step-09/evidence.md).

### Test state

Infrastructure expected results were recorded before VM execution; these replace unit-test red/green for this temporary experiment. Startup and native OTLP acceptance observed; complete read verification and uninterrupted coexistence remain pending. Syntax/Compose safety checks and Brain lint/audit passed. No application persistence code changed. CI will validate the pushed checkpoint.

### Next step

Reserve a stable window with no concurrent core deploy/recreation, repeat the fresh VM baseline, and rerun the bounded native OTLP trial to verify all 60 traces / 120 observations. Do not claim production readiness or merge incomplete trial results as a production integration. Preserve the other task's lease. Draft the permanent same-VM deployment/integration only after a valid acceptance run and the required architecture record.
