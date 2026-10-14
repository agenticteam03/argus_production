# LF-1 — Langfuse capacity trial on the existing Argus VM

Status: baseline verified; temporary trial prepared; VM trial blocked by another active session. Owner: conantkd. VM lease: vm-095 only.

## Goal
Measure whether current Langfuse can coexist with Argus on vm-095 (one CPU, 5900 MiB RAM) under a small synthetic workload. This is not a production integration and does not export real Argus data.

## Scope and expected result
- Six temporary argus-lab-lf1 containers, five dedicated synthetic volumes, existing argus-v18-core network, no published ports.
- Independent Postgres, ClickHouse, Redis and MinIO; no credentials, databases or mounts from Argus.
- Total configured container RAM limit 2816 MiB; CPU quotas sum 0.68 CPU. Initial available RAM must be at least 3800 MiB.
- Abort below 900 MiB available, three consecutive API health failures, an existing Argus service changing/restarting, or the 20-minute trial deadline.
- Headless synthetic project; 60 synthetic traces and 60 spans submitted and verified through the read API. No real model call.
- Monitor Argus /healthz and available RAM before, during and after. Record Docker stats, core restart/OOM state, and immutable image digests.
- A 25-minute independent watchdog cleans up a stalled trial. Normal cleanup removes only the dedicated Compose project and its five new volumes; pulled image caches are retained.
- PASS requires readiness, all traces retrievable, no core state change, no memory guard breach, clean teardown and NO INTERFERENCE.

## Commands and evidence
Commands are archived in brain/execution/history/LF-1/. The infrastructure expected results above replace a red test. No agent rebuild/deploy, persistent tracing configuration, public exposure, ACR application or production data migration is authorized by this trial.

## Limits
API health latency measures responsiveness, not diagnosis quality or representative simultaneous investigation load. A short synthetic test does not establish long-term retention, sustained ingestion or production capacity. The installed tracing backend would require an accepted architecture/deployment record, resource and retention policy, and a separate integration PR.
## Execution interruption

Before upload, the session-marker guard rejected our session 850fe4d2aaf2. Observed marker: dc432c3ff537; both VM leases belong to conantkd / AFTER-MERGE-main / task/AFTER-MERGE-main-2026-10-14. No trial files, images, containers, volumes or watchdog were created on the VM. Do not renew, release or overwrite that other session. Wait for release, claim a new lease, update the expected session in the script and command, and repeat the state/resource probe before running.
