# RB-022 — Stalled job worker

## Metadata

```yaml
id: RB-022
title: Stalled job worker
status: draft
owner: Argus Team
version: 1.0.0
created: 2026-10-27
last_reviewed: 2026-10-27
source_review_date: 2026-10-27
last_tested: null
detector: worker_stalled
```

## Scope

The `argus-lab-jobworker` container on vm-166, its Redis queue store (`argus-lab-cache`), and its declared PostgreSQL dependency (`argus-lab-db`). This runbook diagnoses a symptom; it does not authorize a restart or establish that the worker is the root cause. Apply the shared [runbook conventions](RUNBOOK-CONVENTIONS.md).

## Incident definition

The worker process is alive, but completed-job progress has stopped while a substantial queue is growing. The alert requires the last processed timestamp to be at least three minutes old, queue depth above 10, and positive queue growth over three minutes. The detector also requires a zero five-minute processed-job rate. A healthy HTTP process response alone does not prove the job loop is progressing.

## User / service impact

Determine which jobs are delayed, their age and retry policy, affected consumers, and whether accepted work is at risk of expiry or loss. Queue depth is not a count of unique business requests unless the producer contract guarantees it. Do not inspect job payloads unless an approved, redacted diagnostic explicitly requires them.

## Trigger / detection conditions

`worker_stalled` fires when all three facts hold: `jobs_processed_rate == 0`, `queue_depth > 10`, and `worker_last_processed_age_s >= 180`. The Prometheus `WorkerStalled` alert additionally requires queue depth to be rising. Missing or stale series are unknown, not zero; a short queue or a busy worker with a positive processing rate does not match.

## Symptoms

The worker remains running and its `/health` endpoint responds, but `argus_lab_jobs_processed_total` does not increase. `lab:jobs` grows in Redis and the last processed timestamp becomes older. Producer health can make this symptom more visible but does not identify its cause.

## Plausible causes / hypotheses

| Hypothesis | Evidence needed |
|---|---|
| H1 — Worker loop stalled or unable to complete jobs | Fresh processed-rate, queue and last-processed metrics; worker status and health; bounded worker logs around the last progress time; recent deployment/configuration and resource limits. Compare the worker's own liveness response with actual progress. |
| H2 — Queue store unavailable or unhealthy | Worker-to-cache TCP dependency probe and link history; cache container status and bounded Redis/cache logs; Redis reachability and queue-depth samples from independent telemetry if available. A worker's reported LLEN alone is not independent evidence. |

The cache and worker explanations can coexist. Database trouble is not presumed to affect this Redis-only worker; investigate it only with independent evidence linking it to the incident. A running dependency or a single successful probe does not establish that it is healthy for the complete job operation.

## Required evidence

Use source timestamps and coverage for all three detector metrics, the Prometheus target state, worker/cache identities and statuses, and the declared cache dependency probe. Record the last successful job time, queue trend, scrape gaps, process restart/deployment times and any counter reset. Preserve bounded, redacted logs; never collect job payloads or credentials.

## Required Argus tools

| Existing tool / input | Purpose | Safety class |
|---|---|---|
| `container.status` / `container.health` | Worker and dependency identity and process state | `READ_ONLY_SAFE` |
| `container.logs` | Bounded worker or cache error context | `READ_ONLY_SENSITIVE` |
| `read_link_states` | Recorded dependency probe transitions, when offered | `READ_ONLY_SENSITIVE` |
| `jobs_processed_rate`, `queue_depth`, `worker_last_processed_age_s` | Detect and time the stall | `READ_ONLY_SAFE` |

## Missing tools

Independent Redis queue inspection and worker job-attempt/error metrics are not currently part of this contract. If the worker cannot report queue depth or the dependency probes are absent, record the evidence gap and escalate; do not use arbitrary Redis commands, shell access, SQL, or direct container exec as a substitute.

## Diagnostic workflow

| Step | Action / purpose | Interpret / next step |
|---|---|---|
| 1 | Confirm the worker scrape is up and each detector series is fresh and complete. | Stale, missing, reset or mismatched identity means `insufficient_evidence`; do not treat it as a zero rate. |
| 2 | Compare worker process/health, bounded logs and last-progress time. | A live health response with no progress supports the symptom but does not distinguish H1 from a blocked dependency. |
| 3 | Check the declared cache link, cache state, and queue trend. | A broken or slow cache link supports H2; a running cache alone does not clear it. |
| 4 | Align worker, Redis, scrape and deployment timestamps. | A dependency fault is a victim path; healthy dependencies with direct worker error evidence support H1. Conflicting or missing evidence remains multiple hypotheses. |
| 5 | Preserve evidence and escalate to the owning team with the narrowest supported explanation. | Do not restart a dependency to see whether it helps. A worker restart is considered only after an operator confirms the cause and accepts the bounded risk. |

## Decision tree

```text
required metrics fresh and the three trigger facts hold?
  no -> no worker-stalled incident or insufficient_evidence
  yes -> dependency link/status failure?
           cache -> investigate queue store (H2)
           neither -> direct worker error evidence?
                       yes -> worker loop/runtime (H1)
                       no -> multiple_hypotheses; escalate without restart
```

## False positives and edge cases

No producer or a naturally idle queue; worker startup before its first job; a short-lived burst that drains before evaluation; Prometheus scrape gaps; counter reset or container replacement; duplicate or delayed producer work; a queue-depth metric that is stale; or a process whose health endpoint is responsive while its job operation is blocked.

## Diagnosis outcome

Use `probable_root_cause` only with direct worker or dependency evidence. Otherwise preserve `multiple_hypotheses` or `insufficient_evidence`. The alert and detector identify a stalled-work symptom; they do not prove that the worker itself is at fault.

## Mitigation and action safety

No automatic action is authorized. A scoped `container.restart` of the worker may be proposed only after evidence is preserved, the owner confirms that restart is safe for in-flight/idempotent jobs, and the normal approval and precheck gates pass. Never stop the worker or Redis cache as a diagnostic shortcut. Do not restart the queue store under this runbook.

## Recovery and verification

After an approved change, verify fresh processed-rate increases, a non-growing queue that drains, an advancing last-processed timestamp, a healthy cache dependency probe and no new worker errors. Require three fresh observations spanning at least two scrape intervals, followed by the service owner's stability window. A successful restart command or a healthy `/health` response alone is not recovery evidence.

## Recording / escalation

Record target identities, metric definitions and timestamps, scrape gaps, dependency probe results, bounded redacted log references, competing hypotheses, approval/denial, any action and fresh verification. Escalate worker runtime questions to the platform/worker owner, cache issues to the queue-store owner. No production deployment or fault injection is implied by this draft.

## Lab validation

For the disposable SC-10 fixture, compare normal processing with the injected freeze: the health endpoint stays available while the processed counter stops and queue depth rises; unfreezing resumes processing and drains the queue. Validate the alert's three-minute age and rising-backlog conditions with the configured scrape interval. This scenario has not been executed against a live VM.
