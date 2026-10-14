## 2026-10-14 - LF-2: proposed isolated Langfuse PostgreSQL topology

Type: architecture proposal
Who: conantkd (+ agent)
Context: the user chose separate databases and asked to leave reuse of Argus PostgreSQL open if the initial arrangement does not perform adequately.
Decision / result: proposed ACR-0013. A dedicated Langfuse PostgreSQL service/database/credentials/volume on Host A are the default. The existing Argus PostgreSQL server is a measured fallback with a distinct Langfuse database/login and explicit combined capacity review. No deployment or architecture version change in this proposal PR.
References: [task](../../tasks/current/LF-2-langfuse-db-architecture.md), [ACR](../../architecture/changes/ACR-0013-isolated-langfuse-data-store.md).

### Test state

Documentation-only proposal. Brain lint, audit, link checks and PR CI verify the record. LF-1 startup and one OTLP batch were observed; its full coexistence run was interrupted and is not claimed as passing.

### Next step

Obtain teammate review of ACR-0013. Then rerun LF-1 during a stable VM window, select the measured database arrangement, and place the accepted architecture update and first permanent implementation together in a later PR.
