# OP-003 — Align runbook and capability safety classes

**Status:** proposal drafted; team safety review pending · **Branch:** `task/OP-003-safety-classes` · **Owner:** `conantkd`

## Goal

Give each capability one reviewed safety class that agrees with its runbook usage. Sensitive reads require explicit
output allowlists; writes remain behind the existing closed gate, HITL and precheck.

## This branch

- Proposes [ACR-0005](../../architecture/changes/ACR-0005-capability-safety-classes.md) without changing the
  authoritative architecture or runtime.
- Enumerates all §12.2 capabilities: 17 registered reads already have a class, and 27 planned reads have no runtime
  spec yet. It calls out seven runbook/runtime class disagreements, including mixed labels among runbooks.
- Requires a second team member's approval because the data-minimization and write-gate principles are affected.

## After a decision

1. Review actual output fields for every sensitive read, especially the seven mismatches. Decide whether the output
   should be narrowed or remain sensitive; define allowlists before enforcing registration checks.
2. In one implementation PR, apply the accepted ACR to architecture §12.2–§12.3 and migrate the catalogue and
   policy. Test classification, rejection of unregistered/forbidden operations, allowlist/redaction, and unchanged
   closed write gate. Compare scenario/evaluation behavior before any deployment.
3. Set OP-003 to fixed only when the class inventory and policy enforcement are verified.

No VM access is needed for this proposal.
