## 2026-10-18 — NEXT-PHASE proposal: human-approved remediation, an operator terminal, operator access and audit, more autonomous investigation

Type: decision (proposed)
Who: juanbetancurm and conantkd (+ agents)
Context: Argus diagnoses and recommends; humans repair outside it. The team wants supervised remediation, with a human
operator as the final approver. ARCHITECTURE §14 designs Argus-executed actions but none of it is built (OP-015); the
access model was designed for a read-only UI (password, non-revocable tokens, a shared password still listed in
`SECURITY.md`, OP-016). Two proposals existed: this one (security, terminal, responsibility) and `conantkd`'s "Argus
actúa" (catalogue, cards, colours, prediction, judge, memory, research, scenarios). This PR merges them.
Decision / result: proposed, for team review before any implementation:
- [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md): one account per person, WebAuthn,
  step-up, revocable sessions, explicit permissions, an audit hash chain copied off Host A, privileged routes only on
  a private path;
- [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md): a closed catalogue; service and
  action cards; cited grounds with a computed basis (model-only becomes a suggestion); risk colours that only go up; a
  mandatory prediction and alternatives; a judge that can only make it stricter; a human approves the frozen proposal;
  the worker executes (dispatch reads only frozen rows); verification of the prediction; a memory of verified actions;
  shadow mode for later autonomy; scenario answer keys; lab targets only;
- [ACR-0020](../../architecture/changes/ACR-0020-operator-terminal.md): a recorded, human-only terminal through a
  broker with an SSH CA; "Insert" limited to what the cards allow;
- [ACR-0022](../../architecture/changes/ACR-0022-autonomous-investigation.md): open investigations, follow-up checks,
  new reads, a curated reference corpus and isolated research, all reads and suggestions only.
The plan (phases 15–23, lanes, gates, open decisions) is the task file
[NEXT-PHASE](../../tasks/current/NEXT-PHASE-supervised-remediation.md).
Consequences: nothing changes in the code, the configuration or on the VMs. Earned autonomy, more action families
(PostgreSQL, configuration, rollback, Linux, generated tools) and other runtimes are deferred to later ACRs.
References: [task](../../tasks/current/NEXT-PHASE-supervised-remediation.md), OP-015, OP-016.

### Test state

No code change (documentation only).

### Next step

Team review: accept, change or reject ACR-0018, ACR-0019, ACR-0020 and ACR-0022 (second approvals for the safety
principles) and answer the open decisions in the task file. Then phase 15.
