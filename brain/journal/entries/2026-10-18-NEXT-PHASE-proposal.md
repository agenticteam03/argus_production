## 2026-10-18 — NEXT-PHASE proposal: human-approved remediation, an operator terminal, operator access and audit

Type: decision (proposed)
Who: juanbetancurm (+ agent)
Context: Argus diagnoses and recommends; humans repair outside it. The team wants supervised remediation, with the
operator in control. ARCHITECTURE §14 designs Argus-executed actions but none of it is built (OP-015); the access
model was designed for a read-only UI (password, non-revocable tokens, a shared password still listed in
`SECURITY.md`, OP-016).
Decision / result: proposed, for team review before any implementation:
- [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md): one account per person, WebAuthn,
  step-up, revocable sessions, explicit permissions, an audit hash chain copied off Host A, privileged routes only on
  a private path;
- [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md): actions from runbook menus, a frozen
  proposal approved by a human, an executor that never sees model output, an exact-route gateway, lab targets only,
  verification; and the responsibility model (the approver is accountable for the decision; the team for what is
  proposed, what is shown and what runs);
- [ACR-0020](../../architecture/changes/ACR-0020-operator-terminal.md): a recorded, human-only terminal through a
  broker with an SSH CA; Argus never uses it.
The plan (phases 15–21, lanes, gates, open decisions) is the task file
[NEXT-PHASE](../../tasks/current/NEXT-PHASE-supervised-remediation.md); `IMPLEMENTATION_PLAN.md` lists the phases as
planned; OP-015 and OP-016 record the two inconsistencies.
Consequences: nothing changes in the code, the configuration or on the VMs. `ARCHITECTURE.md`, `SECURITY.md` and
`NETWORK.md` change only when each ACR is applied with its first code. Observed topology, hypotheses and ranking,
incident feedback and controlled external knowledge are later phases with their own ACRs.
References: [task](../../tasks/current/NEXT-PHASE-supervised-remediation.md), OP-015, OP-016.

### Test state

No code change (documentation only).

### Next step

Team review: accept, change or reject ACR-0018, ACR-0019 and ACR-0020 (second approvals for the safety principles)
and answer the open decisions in the task file. Then phase 15.
