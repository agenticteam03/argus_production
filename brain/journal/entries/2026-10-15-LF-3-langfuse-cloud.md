## 2026-10-15 — LF-3 step 02: vm-095 on main 5d4b347; the self-hosted Langfuse failed its capacity gate; ACR-0016 proposes Langfuse Cloud (EU)

Type: deployment + architecture proposal
Who: conantkd (+ agent)
Context: #152 (ACR-0013's tracing code, off by default) and #154 merged. ACR-0013 put six Langfuse services on vm-095
and made enablement wait for a capacity gate.
Decision / result: vm-095 moved to `main` `5d4b347` (backup, one image for agent/worker/scheduler, 20/20, 55/55, WRITE
GATE CLOSED, UI healthy, NO INTERFERENCE). The Langfuse stack started (health 200 in about 60 s, about 2.1 GiB) and the
worker's tracing was switched on, but about 15 minutes later a ClickHouse merge was OOM-killed at its 768 MiB limit and
the host's disk saturated (I/O pressure 99 %, load 176). Argus stayed up but slowed. The stack was stopped (volumes
kept), tracing rolled back and the keys removed; Argus recovered within a minute. The worker reaches Langfuse Cloud
(4.59, EU and US). ACR-0016 proposes the EU Cloud with the same allowlisted spans; the endpoint becomes a worker-only
compose setting (`ARGUS_TRACING_ENDPOINT`, default the private stack).
Consequences: no tracing on vm-095 until ACR-0016 is decided. Two lessons for code.bash: vm-095's `install` is uutils
(refuses a numeric owner: use `umask` + `chown`), and compose names the Langfuse containers
`argus-v18-langfuse-argus-v18-langfuse-<service>-1` (stop them by service name). vm-166's `argus-lab-cache` was found
stopped (since about 22:07, not by this session) and left as found.
References: [evidence](../../execution/history/LF-3/step-02/evidence.md),
[ACR-0016](../../architecture/changes/ACR-0016-langfuse-cloud.md).

### Test state

One new test, `test_the_worker_alone_takes_the_tracing_endpoint_private_by_default` (red seen: `KeyError:
'ARGUS_TRACING_ENDPOINT'`); the tracing and compose tests green.

### Next step

Review of ACR-0016 (juanbetancurm). If accepted: apply ACR-0013 and ACR-0016 to `ARCHITECTURE.md` (the next free version), create the
team's Langfuse Cloud project, LF-3 step 03 on vm-095 (keys, `hosts.env`, worker and agent, one trace, Cloud away),
then remove the stopped self-hosted stack and its volumes. Restore vm-166's `argus-lab-cache` in the next vm-166 session.
