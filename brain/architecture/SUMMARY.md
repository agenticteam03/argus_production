# Architecture summary (v1.8.0)

A two-page orientation. The full, authoritative text is [`ARCHITECTURE.md`](ARCHITECTURE.md); when in doubt, it wins.

## The ideas you must preserve

| Idea | Meaning | Where |
|---|---|---|
| **Fixed safety skeleton** | every investigation runs `detect → recall → investigate ⇄ act → record`; growth is *registered* around it, never edits it | §10 |
| **One guarded tool entry point** | every tool call goes through `InvokeCapability`: validate → budget → audit → policy → provider → redact → store evidence → audit result | §6, §12 |
| **TargetRef(host, kind, name)** | a target is always host-qualified, e.g. `vm-166/container:argus-lab-worker`; the same name on two hosts is two targets | §5 |
| **InventoryPort** | hosts, executors, targets and dependencies come from `config/inventory.yaml` | §8, §12 |
| **Executors resolved per host** | `spec.executor + target.host` → endpoint + credential; **never fall back to another host** | §12 |
| **Evidence stored once, SHA-256** | insert-only evidence and audit records, with host, executor and hash | §15, §16 |
| **Registered incident classes and strategies** | detectors + signals + class entry + runbook; no core change to add a class | §9, §24 |
| **Policy as data** | `config/policy.yaml`: scope, limits, write gate (empty) | §13 |
| **JWT for humans** | operators log in (one user per developer); no write capability is released | §7, §17 |
| **Deterministic before AI** | a healthy check, an unsupported report or stale metrics make **no** model call | §9, §10 |

## Deployment shape (as built)

- **Host A = `vm-095`:** the agent (API on `127.0.0.1:18000`, Postgres without a host port), plus light target services.
- **Host T = `vm-166`:** the primary target host with its own gateway, probes, exporter and Prometheus, published on
  `127.0.0.1` only and reached from vm-095 through a restricted SSH tunnel.
- Details: [`../infrastructure/environment.md`](../infrastructure/environment.md).

## Known differences between the text and the running system

These are recorded here so nobody "fixes" one side silently. Each will be resolved by code (the plan), by a team decision, or by an ACR.

| Topic | Architecture says | Running today | Resolution |
|---|---|---|---|
| Cross-host path (§3.2, §3.6) | §3.6 reference values: private subnet, no tunnel | restricted SSH tunnel over port 22 (the only open port between the VMs) | **pending team decision D-001** (`../OPEN_PROBLEMS.md`) |
| Alerts | Alertmanager webhook push | alerts pulled by `ReconcileFiringAlerts` through the tunnel | **pending team decision D-001** |
| Workflow engine (§10) | LangGraph with a Postgres checkpointer | plain-Python runner | plan Phase 9 (task T-0013) |
| Tools process (§12) | stdio MCP tools child under UID `argus-tools` | direct in-process provider | plan Phase 4 |
| api / worker / scheduler | separate processes | one agent container, no scheduler | plan Phase 9 |
| Runbooks (§2.4) | reviewed copy in the code repository (`argus/runbooks/`) | **resolved by D-002 (2026-10-02):** in `argus/runbooks/`; the VM still mounts the old copy until the next agent redeploy | — |
