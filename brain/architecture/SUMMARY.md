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

## Proposed, not applied (under team review)

The architecture above is unchanged until these are accepted and applied with their first code
([NEXT-PHASE](../tasks/current/NEXT-PHASE-supervised-remediation.md)):

| ACR | Proposes |
|---|---|
| [ACR-0018](changes/ACR-0018-operator-access-and-audit.md) | operator access and audit: one account per person, WebAuthn, step-up, revocable sessions, explicit permissions, an audit hash chain copied off Host A, privileged routes on a private path |
| [ACR-0019](changes/ACR-0019-human-approved-remediation.md) | human-approved remediation: a closed catalogue; service and action cards; cited grounds (a model-only basis becomes a suggestion); risk colours; a prediction; a judge that can only make it stricter; a human approves the frozen proposal; the worker executes through an exact-route gateway; verification and a memory of verified actions; lab targets only |
| [ACR-0020](changes/ACR-0020-operator-terminal.md) | an operator terminal: a recorded, human-only shell from the UI through a broker with an SSH CA; "Insert" offers only what the cards allow; Argus never uses it |
| [ACR-0022](changes/ACR-0022-autonomous-investigation.md) | more autonomous investigation, reads and suggestions only: open investigations for unclassified incidents, follow-up checks after any fix, new reads, a curated vendor corpus, isolated internet research for the operator |

## Deployment shape (as built)

- **Host A = `vm-095`:** the agent (API on `127.0.0.1:18000`, Postgres without a host port), plus light target services.
- **Host T = `vm-166`:** the primary target host with its own gateway, probes, exporter and Prometheus, published on
  `127.0.0.1` only and reached from vm-095 through a restricted SSH tunnel.
- Details: [`../infrastructure/environment.md`](../infrastructure/environment.md).

## Known differences between the text and the running system

These are recorded here so nobody "fixes" one side silently. Each will be resolved by code (the plan), by a team decision, or by an ACR.

| Topic | Architecture says | Running today | Resolution |
|---|---|---|---|
| Cross-host path (§3.2, §3.6) | transport profile `restricted-ssh` (ACR-0003, 1.8.3) | restricted SSH tunnel over port 22 (the only open port between the VMs) | **aligned** by ACR-0003 (D-001 decided; second approval in the T-0022 PR) |
| Alerts | by profile: pull from the Argus-owned Alertmanager in `restricted-ssh` (§7.3) | no alert reaches Argus yet (no Alertmanager, no reconciliation) | **T-0022** implements the pull (phase 7) |
| Workflow engine (§10) | LangGraph with a Postgres checkpointer | **resolved by T-0013 (2026-10-04):** LangGraph runner, checkpoints in Postgres (plain runner kept as rollback) | — |
| Tools process (§12) | stdio MCP tools child under UID `argus-tools` | direct in-process provider | plan Phase 4 |
| api / worker / scheduler | separate processes | one agent container, no scheduler; interrupted runs are not resumed automatically yet | plan Phase 9 (next: T-0014) |
| Runbooks (§2.4) | reviewed copy in the code repository (`argus/runbooks/`) | **resolved by D-002 (2026-10-02):** in `argus/runbooks/`; the VM still mounts the old copy until the next agent redeploy | — |
| UI insights (§7.1 UI routes) | ACR-0017's fields only | ACR-0021 (`accepted`) fields built ahead of the text: host-metrics `thresholds` and heartbeat age (B1, #173, #177); more with B2 to B4 | ACR-0021 is applied to `ARCHITECTURE.md` in one pull request once B4 has merged (T-0045) |
