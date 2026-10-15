# ACR-0015 — Langfuse Cloud (EU) instead of the self-hosted stack on Host A

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | conantkd (+ agent) · 2026-10-15 |
| Accepted by | pending (juanbetancurm) |
| Second approval (safety principle only) | not required: read-only, write gate, host isolation, evidence integrity and the secrets rules are unchanged (§4) |
| Architecture version | applied together with ACR-0013 (still `proposed`, its code merged in #152) at the next free version (`1.8.13`) |
| Task / PR | [LF-3](../../tasks/current/LF-3-langfuse-local-implementation.md) step 02 · PR #156 |

## 1. Detect and explain

ACR-0013 put six Langfuse services on Host A (vm-095: 1 vCPU, 5.9 GiB, no swap) and made production enablement wait
for a capacity gate. LF-3 step 02 ran that gate on 2026-10-14/15
([evidence](../../execution/history/LF-3/step-02/evidence.md)):

- The stack started in about 60 s and used about 2.1 GiB (web 1022 of 1280 MiB, worker 524 of 768 MiB, ClickHouse
  488 of 768 MiB); 2.4 GiB stayed available.
- About 15 minutes later, with no trace yet ingested, a ClickHouse background merge reached its 768 MiB cgroup limit.
  Reclaim inside the cgroup re-read files from disk for minutes: I/O pressure 99.6 %, load average 176. The kernel
  killed `clickhouse-server` (OOM, 01:00:26Z) and Docker restarted it.
- Argus stayed up (health 200, no restart) but shared the saturated disk; a recreate and a database query in that
  window took minutes. Stopping the six services brought I/O pressure to 1.9 % within a minute.

The single CPU and the shared disk are the limit, not the database: ACR-0013's own fallback (the Argus PostgreSQL
server) does not apply ("A failure caused by ClickHouse, web/worker limits or the single CPU is not solved by moving
the database").

## 2. Why the current architecture is insufficient

ACR-0013 §3 chose "self-hosted Langfuse on Host A" and rejected "another VM or managed cloud service" because it "adds
infrastructure outside the team's same-VM constraint". The measurement shows the same-VM choice costs the Argus host
its disk headroom. ACR-0013 §5 says "If neither arrangement passes, defer the permanent deployment"; this ACR proposes
the alternative it rejected instead of deferring, with the measurement as the reason.

## 3. Smallest reasonable change

The worker sends the same filtered OTLP spans to **Langfuse Cloud, EU region** (`https://cloud.langfuse.com`, Langfuse
4.59 on 2026-10-15, the v4 ingestion header the exporter already sends). Nothing else changes in Argus:

- **Endpoint:** a deployment setting. `compose.core.yml` passes `ARGUS_TRACING_ENDPOINT` to the worker only, default the
  private `http://argus-v18-langfuse-web:3000/api/public/otel/v1/traces` (ACR-0013 unchanged when unset). vm-095's
  `hosts.env` sets `https://cloud.langfuse.com/api/public/otel/v1/traces`.
- **Keys:** a Cloud project key pair, in the same worker-only files (`langfuse_public_key`, `langfuse_secret_key`,
  0400, uid 10010), typed on the VM with a hidden prompt. Never in the API, the UI, a log or the repository.
- **What leaves Host A:** exactly the attributes `test_nothing_sensitive_is_exported` allows (`tracing.py` `ALLOWED`,
  `ROOT_KEYS`): incident id and attempt, incident class, strategy, outcome, node, capability, status, error category,
  step, `decided_by`, evidence id, **the host's inventory name** (`argus.host`: `vm-095`, `vm-166`) and the target
  kind; on a model call the model id, finish reason and token counts; durations. Never prompts, replies, tool
  arguments or results, evidence bodies, container or target names, addresses, ports, credentials, approval payloads.
  (`deploy/langfuse/README.md` acceptance step 4 says "no … host names": the code exports the inventory name, which
  is not an address; step 03 checks the trace against this list, not the README's.)
- **The trace link:** `ARGUS_LANGFUSE_UI_URL=https://cloud.langfuse.com` and the Cloud project id; operators and
  approvers only, a link, never Langfuse data (ACR-0013 C).
- **Access:** the team's Cloud organization, each member with their own login. No Langfuse port on Host A.
- **The self-hosted stack:** stays in `deploy/langfuse/` as the reviewed alternative for a host with headroom; it is
  stopped on vm-095 and its volumes are removed in the next leased session once this ACR is accepted.

Architecture text when applied (with ACR-0013): §18.5 "This is optional." → "This is optional (ACR-0013, ACR-0015):
the worker exports filtered OTLP spans to Langfuse Cloud (EU) through `ARGUS_TRACING_ENDPOINT`; a self-hosted stack
(`deploy/langfuse/`) is the alternative for a host with headroom. Telemetry never replaces audit and never blocks an
investigation." Plus a §3.3 communication-matrix row (`argus-worker` → Langfuse Cloud, HTTPS egress, filtered traces, the Langfuse project key pair) beside the model endpoint row, and the Langfuse keys in the worker's row of the credentials table (§17.2).

**Alternatives considered:**

- **Tune ClickHouse for low memory and retry on Host A** (cap `max_server_memory_usage`, smaller caches and merge pool,
  system log tables off). Possible, but the web (1 GiB) and worker (0.5 GiB) still share one CPU and disk with Argus,
  and a tuned ClickHouse still merges on that disk. A second measured attempt is reasonable only if Cloud is refused.
- **Langfuse on vm-166.** Moves the load onto the monitored target host: it would perturb the lab and the very signals
  Argus reads (host isolation in spirit), and vm-166 has the same size.
- **Defer (ACR-0013 §5).** Keeps no observability; the Agent page and the trace link stay empty.
- **US region.** Same service; EU chosen for data residency.

## 4. Consequences

- **Code:** none in `argus/`; `Settings.tracing_endpoint` already reads `ARGUS_TRACING_ENDPOINT`. One compose line and
  one test (`test_the_worker_alone_takes_the_tracing_endpoint_private_by_default`).
- **Deployment:** vm-095 `hosts.env` three lines, two key files, the worker and agent recreated. Egress to
  `cloud.langfuse.com:443` from the worker already works (checked 2026-10-15: `/api/public/health` 200).
- **Cost and limits** (langfuse.com/pricing, read 2026-10-15): every trace and observation is one unit. **Hobby**
  (free): 50k units a month, 30 days of data, **2 users**, a GDPR DPA, EU region. **Core** ($29 a month): 100k units,
  90 days, unlimited users. One attempt is about 8–30 units (a root, five or six node spans, one per capability read:
  `ARGUS_MAX_STEPS` 8 × `ARGUS_MAX_READS_PER_STEP` 2 at most, one per model call), so Hobby holds roughly 1,700
  investigations a month, about 55 a day: well above the lab's alert and manual load (the scheduled check is
  disabled). The §21.2 evaluation does not trace: `run_case` swaps in a throwaway secrets folder without the key files.
  The 2-user limit is the real constraint (three developers are onboarded): the team either names two users or takes
  Core. A refused or throttled export only drops telemetry (fail-open, counted, logged once): the run, its audit and
  its records are unchanged. The exporter sends at most one batch of 64 spans every 2 s, far below the 1,000
  requests a minute ingestion limit.
- **Risk:** span metadata (incident ids, class, capability and host inventory names, durations, tokens) is stored by
  a third party.
  Mitigated by the allowlist above, which ACR-0013's tests (`test_nothing_sensitive_is_exported`) already enforce.
- **How to reverse it:** `ARGUS_TRACING_ENABLED=0` (or remove the key files) and recreate the worker; delete the Cloud
  project. Nothing in Argus's database or audit depends on Langfuse.
- **Safety principle:** no. Read-only and the write gate are untouched; no Host-T component talks to Langfuse; the
  secrets rule holds (keys only in the worker's 0400 files); audit stays the evidence of record.

## 5. Decision

Proposed: export the worker's filtered traces to Langfuse Cloud (EU) instead of a stack on Host A, because the
measured self-hosted stack saturated Host A's disk. Awaiting juanbetancurm's review.

## 6. Applied

- [ ] Accepted in the PR review.
- [ ] `ARCHITECTURE.md` §18.5, §3.3 and the §17.2 credentials row updated with ACR-0013 and this ACR, version `1.8.13`, changelog line.
- [ ] vm-095: Cloud keys and `hosts.env`, worker and agent recreated; one trace seen in Langfuse Cloud with nothing
      outside the allowlist; a run with Cloud unreachable still records and audits.
- [ ] The stopped self-hosted stack and its volumes removed from vm-095.
