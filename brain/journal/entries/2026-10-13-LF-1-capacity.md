## 2026-10-13 — LF-1: initial Langfuse capacity baseline; guarded trial blocked

Type: infrastructure experiment preparation
Who: conantkd (+ agent)
Context: the user requested testing self-hosted Langfuse on the same VM as Argus. Runtime probes were observed on 2026-10-14 UTC (2026-10-13 America/Bogota).
Decision / result: vm-095 has one CPU, 5900 MiB RAM, 4408 MiB available and 73846 MiB free disk. Existing core services run without restarts or OOM; /healthz returned 200; LAB BASELINE OK and NO INTERFERENCE. Six candidate images advertise arm64. Prepared a bounded six-service synthetic-only trial with dedicated volumes, no host ports and normal/fallback cleanup.
The upload guard stopped execution because another session took both VM leases and changed the VM marker. No trial stack or credentials were created. No conclusion about actual Langfuse startup, ingestion or sustained coexistence can be made yet. Existing Argus deployment was not changed by this task.
References: [task](../../tasks/current/LF-1-langfuse-capacity.md), [baseline](../../execution/history/LF-1/step-01/evidence.md), [blocked trial](../../execution/history/LF-1/step-02/evidence.md).

### Test state

Infrastructure expected results recorded before execution. Python harness compilation passed; Brain lint/audit clean. Compose structure checked locally for no ports or privileged services, six dedicated services, explicit CPU/RAM caps and five dedicated volumes. Actual Docker/VM execution remains pending.

### Next step

Wait for AFTER-MERGE-main's VM lease release; claim a fresh vm-095 lease, update the marker guards, repeat the baseline, and run the temporary synthetic capacity trial. Do not release the other task's lease.