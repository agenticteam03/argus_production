# Glossary

| Term | Meaning |
|---|---|
| **ACR** | Architecture Change Record: the only way to change `ARCHITECTURE.md` (`architecture/changes/`) |
| **Audit record** | an insert-only row recording who/what did something (tool requested, completed, refused, …) |
| **Capability** | a named tool Argus may call (e.g. container status, log search), described by a `CapabilitySpec` |
| **Check** (`--check`) | a cheap health check: if no symptom is detected, no model call is made (`no_incident`) |
| **Class** (incident class) | a registered kind of incident (e.g. `container_restart_loop`) with a detector, signals and runbooks |
| **Deploy key** | a read-only SSH key on a VM that can fetch this repository and nothing else |
| **DEPLOYED** | `/opt/argus-v18/DEPLOYED`: which commit runs on that VM (written by `ops/deploy.sh`) |
| **Detector** | deterministic code that decides from metrics whether a class applies, before any AI |
| **Escalation** | Argus stops and hands the incident to a human, with the evidence it has |
| **Evidence** | the stored result of a read, insert-only, with host, executor, time and SHA-256 hash |
| **Evidence pack** | a fixed set of reads collected without a model, for unsupported or undiagnosable incidents |
| **Executor** | the service that performs reads on a host: read gateway, host probe, network probe, Prometheus |
| **Handoff** | the note left on the `session` branch when a task is unfinished: branch, last verified step, next step |
| **Host A / Host T** | the agent host (`vm-095`) / the primary target host (`vm-166`) |
| **`hosts.env`** | VM-local file with the VMs' private addresses; never committed |
| **InventoryPort** | the interface that reads `config/inventory.yaml`: hosts, executors, targets, dependencies |
| **InvokeCapability** | the single guarded entry point for every tool call (validate → policy → execute → evidence → audit) |
| **Lease** (session lease) | who currently "owns" the VMs; 60 minutes, renewed automatically; `brain.py start/renew/release` |
| **NO INTERFERENCE** | the result of `nonint-check.sh after`: nothing that is not ours changed |
| **Observation** | the normalized answer of one executor call (status, values, error category) |
| **Outcome** | how an incident ended: `diagnosed`, `escalated`, `undiagnosable`, `unsupported_escalated`, `refused`, `no_incident` |
| **Protected objects** | the pre-existing WireGuard deployment and what it uses; never touched |
| **Recall** | the step that retrieves runbook passages for the incident |
| **Red seen** | proof that a new test failed for the right reason before the code was written |
| **Runbook** | a procedure document in the separate library `agenticteam03/runbooks` (RB-001 …), pinned by commit |
| **Skeleton** | the fixed node sequence `detect → recall → investigate ⇄ act → record` |
| **State probe** | the read-only first step of a VM session: deployed commit, containers, health, nonint-check |
| **Strategy** | how an incident class orders its investigation (which evidence first) |
| **TargetRef** | `host/kind:name`, e.g. `vm-166/container:argus-lab-worker` — the host is always part of the name |
| **Tunnel** (`argus-v18-tunnel`) | the restricted SSH tunnel from vm-095 to vm-166's loopback ports |
| **Write gate** | the policy list of allowed write actions; it is **empty** (Argus is read-only) |
