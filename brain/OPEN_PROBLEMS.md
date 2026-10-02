# Open problems and pending team decisions

When a problem is fixed, set its status to `fixed` with the date, and add a journal entry if it is significant.
**Status:** `open` · `in progress` · `fixed` · `dropped` (with reason) · decisions: `pending` · `decided`

| ID | Item | Status | Opened |
|---|---|---|---|
| **D-001** | Cross-host path and alert direction: architecture text vs the running system | **pending team decision** | 2026-10-02 |
| OP-001 | Runbook `detector` metadata uses old or empty class names | open | 2026-09-30 |
| OP-002 | P0 safety gaps of the runbook library not yet reconciled with architecture v1.8 | open | 2026-09-30 |
| OP-003 | Runbook safety classes not mapped to `CapabilitySpec.risk` | open | 2026-09-30 |

---

## D-001 — Cross-host path and alert direction (pending team decision)

**Status:** pending · **Opened:** 2026-10-02 · **Decided by:** the whole team (including `conantkd`)

**The difference.** Architecture §3.6 (reference values) says the two hosts talk over the **private network with no
tunnel**, and that alerts are **pushed** (Alertmanager on vm-166 → webhook on vm-095). The running system uses a
**restricted SSH tunnel** over port 22 (the only port open between the VMs) and **pulls** alerts through it
(`ReconcileFiringAlerts`), because the cloud network rules cannot be changed by the team.

**Options.**
- **A. Keep the architecture text; change the deployment later.** If someone with access to the cloud console opens
  the needed ports between the private addresses, switch to the private network and push alerts. Only the inventory
  URLs, the compose port bindings and the alert route change; the tunnel is removed.
- **B. Change the architecture to match the running system** through an ACR (§3.6: SSH tunnel, pulled alerts).
- **C. Use the existing WireGuard tunnel** — only with `conantkd`'s agreement, since it belongs to the protected
  deployment.

**Until decided:** the running system stays as it is (tunnel + pull). Nobody changes the architecture text or the
transport alone.

**Done when.** The team has chosen; the result is either an accepted ACR (B) or a planned task (A or C), recorded in
the journal.

---

## OP-001 — Runbook `detector` metadata uses old or empty class names

**Status:** open · **Opened:** 2026-09-30

**Problem.** Each runbook in the library (`agenticteam03/runbooks`, `runbooks/RB-*.md`) has a `detector:` field. It
still uses v1.7 names or is empty: RB-001 `oom_restart_loop` (v1.8: `container_restart_loop`, shared with RB-008);
RB-002 `health_check_failed` and RB-003 `dependency_unavailable` already match; RB-004…RB-021 `null`. Architecture
§15.3 requires that "a runbook's `detector` metadata names the class that uses it".

**Fix.** In the runbooks repository: set `detector:` in every runbook to its v1.8 class (§1.3); bump `version` and
`last_reviewed`; update `RUNBOOK-INDEX.md`. Then move the pin in `config/runbooks.lock`.

**Done when.** All 21 runbooks name a class that exists in §1.3, and a check shows no class without a runbook and no
runbook without a class.

---

## OP-002 — P0 safety gaps not yet reconciled with architecture v1.8

**Status:** open · **Opened:** 2026-09-30

**Problem.** The library's `ARGUS-CAPABILITY-GAPS.md` lists eight **P0** gaps written against an older code base.
Each must be settled in the architecture (ACR) before the related implementation. First assessment — to be verified:

| Gap | Asks for | Against v1.8 | Likely change |
|---|---|---|---|
| G-001 Deployment profiles | named, versioned profiles (production / lab); missing profile fails closed | partial: per-(capability, target) write gate, no profile | `profile` in the policy file; write gate evaluated per profile |
| G-002 Typed prerequisites | preconditions as typed predicates on fresh, identity-bound evidence | **missing**: §13.1 uses free-text `preconditions` | typed predicates evaluated at `propose_action` and `precheck_action` |
| G-003 Observation provenance | source vs collection time, coverage, units, partial state, identities | partial | add the fields to `Observation` / `EvidenceRecord`; missing is never zero or healthy |
| G-004 Approval binding | immutable proposal bound to what it acts on, previews | mostly covered | extend `identity()`; preview in the approval view |
| G-005 Verification windows | stability windows, provisional vs final recovery | partial | `stability_window` per class; provisional/final states |
| G-006 Data minimization | per-source field allowlists, literal redaction | partial | `allowed_fields` per `CapabilitySpec` |
| G-007 Helper semantics | missing/partial data never becomes healthy or root cause | principle missing (implemented for metrics freshness) | state the rule in §12.3; contract fixtures |
| G-008 Corpus/dispatcher separation | runbook IDs from metadata, bounded passages, tools never from runbook text | covered by §15.3 | verify that writes are offered only for registered classes |

**Done when.** Each gap is covered, changed through an ACR, or dropped with a reason.

---

## OP-003 — Runbook safety classes not mapped to `CapabilitySpec.risk`

**Status:** open · **Opened:** 2026-09-30

**Problem.** The library's conventions classify operations as `READ_ONLY_SAFE`, `READ_ONLY_SENSITIVE`,
`MUTATING_LOW_RISK`, `MUTATING_HIGH_RISK`, `FORBIDDEN`; architecture §12.3 uses `risk: low | medium | high | very_high`
plus `permission: read | write_hitl`. They do not map cleanly (sensitive reads need allowlists; `FORBIDDEN` has no
equivalent).

**Fix (to discuss, ACR).** Adopt the five classes as `safety_class`, derive `permission` from it; sensitive reads get
mandatory field allowlists (ties to G-006); `FORBIDDEN` operations are never registered; classify every capability in §12.2.

**Done when.** §12.3 has one scheme; every capability has a class; policy and redaction rules refer to it.
