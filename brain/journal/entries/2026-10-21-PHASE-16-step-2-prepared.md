## 2026-10-21 — Phase 16 step 2 prepared: the agent mounts the Ed25519 key

Type: implementation
Who: conantkd (+ agent)
Context: step 1 built EdDSA signing behind the secret `jwt_ed25519_key`; the lab switches on when the agent mounts it.
Decision / result:
- `deploy/vm-095/compose.core.yml`: the agent mounts `jwt_ed25519_key` as a single file, like `jwt_signing_key`
  (`tests/test_compose_split.py` lists it). The worker already sees the whole folder; it signs nothing.
- `execution/history/PHASE-16/step-02/code.bash`: the key is generated on vm-095 before any `up` (a missing bind
  source would become a directory and the API would not start), owned and moded like `jwt_signing_key`, never
  printed; then the first `prune-sessions` dry run (#240).
- ACR-0018 §6 records the session retention (#240) and this step.
Consequences: after the deploy every session logs in again. Rollback: remove the mount line and recreate the agent.
References: [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md),
[PHASE-16](../../tasks/current/PHASE-16-operator-access.md).
