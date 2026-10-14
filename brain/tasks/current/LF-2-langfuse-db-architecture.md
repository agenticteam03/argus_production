# LF-2 - Langfuse database topology ACR

Status: proposed for PR review. Owner: conantkd. Code-only documentation task; no VM lease or production mutation required.

## Goal

Record the team's decision to start self-hosted Langfuse on Host A with its own PostgreSQL service, while allowing a separate-database fallback on the existing Argus PostgreSQL server only after measured capacity and connection budgeting.

## Deliverable

[ACR-0013](../../architecture/changes/ACR-0013-isolated-langfuse-data-store.md) is a proposal. Its PR does not apply the architecture or deploy Langfuse. Review of the ACR precedes the implementation PR, which must update `ARCHITECTURE.md`, bump its version/changelog, and include the first deployment code together.

## Evidence and gate

The [LF-1 trial checkpoint](https://github.com/agenticteam03/argus_production/blob/a6cc843/brain/tasks/current/LF-1-langfuse-capacity.md) established startup and one accepted OTLP batch on vm-095. A concurrent Argus recreation stopped the complete read/coexistence run. Before permanent deployment, repeat its 60-trace / 120-observation gate in a stable window. If a separate PostgreSQL service fails the gate, identify the bottleneck before trying the existing server; never treat mere version compatibility as enough.

## Scope boundary

No VM commands, persistent database changes, public Langfuse listener, agent instrumentation or architecture version change in this ACR PR.
