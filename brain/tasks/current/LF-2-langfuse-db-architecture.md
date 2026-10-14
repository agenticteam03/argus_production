# LF-2 - Argus agent observability with Langfuse ACR

Status: proposed in PR #150. Owner: conantkd. Documentation-only architecture decision; no VM lease or production mutation is required for this PR.

## Goal

Define the full optional Langfuse integration for the Argus worker on Host A: services and network, trace boundaries, filtered data, secrets, failure behaviour, database ownership and an acceptance gate. Start with a separate Langfuse PostgreSQL service while leaving the existing Argus PostgreSQL server as a measured fallback.

## Deliverable

[ACR-0013](../../architecture/changes/ACR-0013-langfuse-agent-observability.md) is the review proposal. It specifies OTLP tracing of LangGraph execution attempts, model and tool calls; the six-service same-VM stack; and how the existing Argus telemetry and audit remain distinct. The first implementation PR, after acceptance, updates `ARCHITECTURE.md`, bumps its version/changelog, and includes the first code and deployment configuration together.

## Evidence and gate

The [LF-1 trial checkpoint](https://github.com/agenticteam03/argus_production/blob/a6cc843/brain/tasks/current/LF-1-langfuse-capacity.md) observed startup and one accepted OTLP batch on vm-095. Concurrent Argus recreation stopped complete read/coexistence verification. Before permanent deployment, repeat the 60-trace / 120-observation gate in a quiet window and exercise the real Argus exporter with Langfuse healthy and unavailable. Evaluate Argus PostgreSQL reuse only if measurements identify the separate PostgreSQL process as the bottleneck and the combined budget is safe.

## Scope boundary

This PR is a proposed ACR only: no VM commands, persistent database changes, Langfuse public listener, agent instrumentation or architecture version change.
