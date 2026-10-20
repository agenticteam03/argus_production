## 2026-10-20 — Phase 15 foundations: OP-015 and OP-016 fixed, the action path protected

Type: implementation
Who: conantkd (+ agent)
Context: phase 15 of the [NEXT-PHASE plan](../../tasks/current/NEXT-PHASE-supervised-remediation.md) (#170 merged):
fix OP-015 and OP-016, and extend `SELF_MERGE_PROTECTED` before anything can act. Three items, one pull request.
Decision / result:
- **OP-015 fixed:** ARCHITECTURE §14 says the approval and action machinery is **designed, not built** (1.8.21); the
  plan's phase 9 and its "Escalation / approval" exit line no longer list HITL against a fake endpoint (phase 18).
- **OP-016 fixed:** `policies/SECURITY.md` lists "Each developer's Argus password (one account per person, no
  shared login)" instead of a shared team password. The read-only `principal` query on vm-095 (run by conantkd)
  shows five personal `human` principals, two of them disabled (`conantkd-viewer`, `olav`); no shared account.
- **`SELF_MERGE_PROTECTED`** gains the action path before it exists: `config/actions/`, `config/risk.yaml`,
  `config/ranking.yaml` (ACR-0024), `argus/capabilities/write_contract.py`, and the reserved names `argus/actions/`
  (the dispatch module) and `services/action-gateway/`. `REVIEW_PROTOCOL.md` lists them; `tests/brain` covers each.
- The NEXT-PHASE status says the plan is approved (its ACRs are still `proposed`).
Consequences: the first PR that builds the dispatch module or the gateway uses those names, or updates the list in
the same PR. Nothing left for OP-015 or OP-016.
References: [OPEN_PROBLEMS](../../OPEN_PROBLEMS.md) OP-015, OP-016; ACR-0019; #170.
