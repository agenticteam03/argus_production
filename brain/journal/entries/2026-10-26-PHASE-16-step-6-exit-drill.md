## 2026-10-26 - PHASE-16 step 6: migration 016 deployed; the tamper drill detects an edited audit row

Type: implementation (deploy step and drill)
Who: conantkd (+ agent)
Context: #342 merged (`6e87828`, migration 016). ACR-0018 step 6 asks for a tamper drill on vm-095.
Decision / result:
- vm-095 runs `main` `6e87828`: backup verified, migration 016 applied (schema 001-016), agent, worker and scheduler
  rebuilt; 91/91 database checks; the audit chain verified. vm-166 unchanged.
- The drill: the owner added one key to a chained audit row. `argus audit verify` and the scheduler's chain check both
  named that row (`hash does not match its body`), and the digest job refused to sign the broken chain. The key was
  removed and both checks verified the chain again.
Consequences: phase 16's exit proof holds except the two step 5 follow-ups: the scheduler's outbound allowlist and the
team's alert receiver.
References: [evidence](../../execution/history/PHASE-16/step-06-exit-drill/evidence.md), ACR-0018 step 6, #342.

### Test state

On the VM: `91/91 database checks passed`; in the drill `AUDIT CHAIN BROKEN: 1 problem(s)` then `AUDIT CHAIN OK: 318
rows chained`; vm-095 and vm-166 `NO INTERFERENCE`. CI green on `6e87828`.

### Next step

The scheduler's outbound allowlist (OCI only), then the team's alert receiver; phase 16 is then done.
