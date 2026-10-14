## 2026-10-14 — ACR-0012 built on a local branch: the UI may start an investigation

Type: feature (API, edge, frontend)
Who: conantkd (+ agent)
Context: ACR-0012 is proposed (#147 merged the record, not its acceptance). `conantkd` asked to build it without a
PR yet, on `task/ACR-0012-impl`.
Decision / result:
- **The `investigate` token:** every GET and `POST /api/v1/investigations` only. The edge issues `read` or
  `investigate`, never full.
- **Quotas for investigate tokens:** 10 an hour and 2 queued per account, 20 queued in all, answering 429 with
  `Retry-After`.
- **`GET /api/v1/targets`.**
- **The audit:** `investigation.requested` and `investigation.quota_refused`.
- **The contract and the edge:** one POST location with its own limit.
- **The UI:** a form on the dashboard, "Investigate again" on an incident, shown only when `/me` allows it, and a
  guard that allows that one POST only then.
- ARCHITECTURE 1.8.11 applied on the branch.

**One difference from the ACR, recorded in its §7:** the quotas apply to investigate tokens only. A full token is
loopback only (the CLI and the E2E runner) and is not limited.

Consequences: nothing deployed; the public UI still runs read-only `main`. Before enabling it in public, the shared
`operator` accounts mean an investigation cannot be attributed to a person (ACR-0012 §4).
References: [ACR-0012](../../architecture/changes/ACR-0012-ui-start-investigation.md),
[T-0016](../../tasks/current/T-0016-frontend.md).

### Test state

- `tests/test_acr0012_investigate.py` 16 (12 red seen); edge tests 29; contract 3.
- Frontend: unit 85, acceptance 14 (stable four times), lint 0 errors.

### Next step

Its PR when `conantkd` says so (a teammate's approval and the second approval), then the AFTER-MERGE on vm-095 (the
agent and the edge).
