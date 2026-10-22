## 2026-10-22 - DEPLOY-afb72e8 prepared (EdDSA, Vite 8 UI, contrast fix); not run by the agent

Type: deploy
Who: conantkd (+ agent)
Context: main `afb72e8` carries everything merged since vm-095's `6c83da3`: phase 16 step 2 (EdDSA, #241),
`db prune-sessions` (#240), T-0047 H4 and H5 (H5 offered to no class), Vite 8 (#242) and the contrast fix (#257).
Decision / result:
- `execution/current/code.bash` holds the deploy: both leases; backup; checkout; the Ed25519 key generated on vm-095
  before any `up` (never printed, owned and moded like `jwt_signing_key`); agent, worker and scheduler on one image;
  `argus deploy record`; the UI rebuilt; the read-only checks (EdDSA on, H5 registered, `db check`, `audit verify`);
  the first `prune-sessions` dry run; `nonint-check` before and after on both VMs.
- No migration (the database stays at 012); vm-166 unchanged (nothing under `services/` or `deploy/target/`).
- The agent took both leases at night to run it, but its permission rules refuse remote writes (the SESSION marker),
  so nothing was changed on either VM and the leases were released at once.
Consequences: `conantkd` runs the code.bash; every open session logs in again once the key is mounted.
References: [code.bash](../../execution/current/code.bash), PHASE-16 step 2
([code.bash](../../execution/history/PHASE-16/step-02/code.bash)), DEPLOY-189 (the UI rebuild).
