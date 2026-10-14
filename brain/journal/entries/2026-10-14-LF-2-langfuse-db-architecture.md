## 2026-10-14 - LF-2: proposed Langfuse agent observability architecture

Type: architecture proposal
Who: conantkd (+ agent)
Context: the user selected Langfuse on the Argus VM, chose separate databases initially, left Argus PostgreSQL reuse open if performance requires it, and requested that ACR-0013 cover the full agent observability integration.
Decision / result: proposed a six-service Langfuse stack on Host A and optional, filtered OTLP spans from the Argus worker for investigation attempts, graph nodes, model and capability calls. No raw evidence, prompts or secrets are exported by default. Telemetry failure does not block investigations or audit. Langfuse starts with its own PostgreSQL service; the existing Argus server is a gated separate-database fallback. No deployment or architecture version change in PR #150.
References: [task](../../tasks/current/LF-2-langfuse-db-architecture.md), [ACR](../../architecture/changes/ACR-0013-langfuse-agent-observability.md).

### Test state

Documentation-only proposal. Brain lint, audit and PR CI verify the record. LF-1 startup and one native OTLP batch were observed; full coexistence remains unverified after a concurrent Argus recreation.

### Next step

Obtain teammate review of ACR-0013. In the first implementation PR, update the architecture version/changelog with the implementation, exercise filtered span and exporter-failure tests, and rerun the VM capacity gate in a stable window before enabling permanent tracing.
