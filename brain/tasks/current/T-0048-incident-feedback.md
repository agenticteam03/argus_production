# T-0048 — Memory and feedback: was the diagnosis right, and what fixed it

| Field | Value |
|---|---|
| Status | `proposed` - [ACR-0029](../../architecture/changes/ACR-0029-incident-feedback.md) acceptance by `conantkd` pending; WebAuthn and step-up are implemented on main and deployed on vm-095; the private path and off-host audit digest remain unmet; no T-0048 implementation |
| Phase | next phase, area G (separate track of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md)) |
| Architecture | [ACR-0029](../../architecture/changes/ACR-0029-incident-feedback.md) (`proposed`); depends on ACR-0018 |
| Owner | `juanbetancurm` (+ agent); review: `conantkd` |
| Needs the VM lease | the deploy only |

## Goal (plain language)

An operator can say, for each incident, whether Argus was right, what the real cause was, what fixed it and whether it
stayed fixed. Later investigations, the similar-case search and the ranking weights of
[T-0047](T-0047-hypotheses-cause-ranking.md) learn only from these **confirmed** cases.

## What the ACR will cover (from the next-phase plan, area G)

- Insert-only `incident_feedback` (verdict, actual class and root-cause target, fix kind and a redacted summary;
  corrections are new rows) and `incident_verification`; an `incident_outcome` view.
- `POST /api/v1/incidents/{id}/feedback`: human only, a `feedback` permission, step-up when it labels a cause
  (ACR-0018).
- `knowledge.prior_incidents` gains `confirmed_only`; a failed fix is never a precedent for that fix.
- Case similarity (`incident_features`, an interpretable weighted match) and a prior for the T-0047 ranking.
- An offline export of a confirmed incident to a draft evaluation case, reviewed in a PR, never automatic.

## Why it waits

Labels steer future diagnoses, so they are privileged writes: they need the per-person accounts, step-up and audit of
ACR-0018 first. Until then, T-0047 ranks with evidence weights only.

## ACR-0018 gate status (snapshot: main `f480152`; vm-095 deployment `77c4524`)

For this table, `met` means the gate implementation is merged and, for vm-095, deployed according to its record. It does
not mean operator credential enrollment or a feedback-route operation has been exercised. PR #288 is open; its
deployment evidence is on that PR branch. The record says the reciprocal enrollment tickets and two-key registration
remain to be done.

| ACR-0018 gate | Main `f480152` | vm-095 | Evidence |
|---|---|---|---|
| WebAuthn second factor | Met | Met (deployed; operator enrollment pending) | Main: `deploy/migrations/013_webauthn.sql`, `argus/adapters/inbound/http.py`, `tests/test_acr0018_webauthn.py`; PRs #280/#284. vm-095: PR #288 `brain/execution/history/DEPLOY-77c4524/step-01/evidence.md` records migration 013 and the relying party set. |
| Step-up token | Met | Met (code deployed; live privileged use not recorded) | Main: migration 013, `argus/adapters/inbound/http.py`, `tests/test_acr0018_webauthn.py`; PR #280. vm-095: PR #288 records deployment of #280's migration 013 and code at `77c4524`; its checks do not exercise a privileged step-up operation. |
| Private path (mTLS and allowlist) | Not met | Not met | `brain/tasks/current/PHASE-16-operator-access.md` step 4 and `brain/architecture/changes/ACR-0018-operator-access-and-audit.md` say it is not yet built; PR #288 records step 3 only. |
| Signed off-host audit digest/protection | Not met | Not met | Phase 16 step 5 and ACR-0018 completion notes leave the signed daily digest off Host A pending. PR #288 verifies the on-host audit chain (137 rows), not an off-host digest. |

After conantkd accepts ACR-0029 and its decisions, the first allowed implementation slice is the insert-only feedback
and verification tables, outcome projection/use cases, minimum grants, and SQLite/Postgres tests, with no HTTP route.
Keep feedback writes unavailable and `prior_weight=0`. Do not deploy or expose the route until the private-path and
off-host audit gates are met on the deployed profile and the route/edge authorization checks receive team approval.

## Acceptance decisions (proposed answers)

[ACR-0029 §5](../../architecture/changes/ACR-0029-incident-feedback.md#5-decision) leaves six decisions to the team.
These are recommendations for that discussion, not decisions: accepting the ACR (and recording the answers there) is
the team's call in its own PR. Numbers marked *OD-7* are starting values to be set from measurements (§25 OD-7).

| # | Decision | Options | Recommendation | Why |
|---|---|---|---|---|
| 1 | Who may label | (a) the three operators with ACR-0018's `feedback` grant; (b) narrower cause-label authority; (c) (a) plus a second operator for disputed labels | **(c)**: keep the grant; on the production profile a label that contradicts the original diagnosis (`incorrect`, or a different cause) needs a second operator's confirmation before it counts as `confirmed_cause`; on the lab profile one operator is enough | Labels steer later diagnoses; a contradiction is where one person's mistake does most harm. Mirrors the production/lab split of ACR-0018's separation of duties (that rule is requester ≠ approver for actions; this one is analogous). No new grant. |
| 2 | Step-up for which writes | (a) every feedback write; (b) cause labels only, notes exempt | **(a)** in the first release | One code path and one test matrix; a "note" that recall or ranking can read is a label in practice. Revisit an exemption only with a note type that nothing reads (ACR-0029 §3.2). |
| 3 | Confirmation and stability | window, freshness, coverage, recurrence rule | Observation window = the incident's recorded window; freshness bound = `METRICS_MAX_STALENESS`; stability = 30 min with at least 80 % of expected samples (*OD-7*); a same-class incident on the same target within 7 days removes `fix_usable` (*OD-7*); approve the evidence rules of §3.1 as written | Reuses bounds Argus already has instead of new ones; short enough to verify a lab fix in one session; the recurrence rule stops a fix that only masked the cause from becoming a precedent. Unknown stays unknown. |
| 4 | Retention | periods; evidence pruning; export policy | Feedback and verification rows: same class as episodic state (§16, category 4), at least 1 year; referenced evidence is never pruned while an active head cites it (the maintenance job checks the reference first); if cited evidence is pruned anyway, `confirmed_cause` and `fix_usable` fall to unknown; export only by an `admin` principal, offline, reviewed in a PR | Keeps provenance at least as long as the eligibility it justifies (§5 item 4); fails closed when provenance is gone; export stays a deliberate, reviewed act. |
| 5 | Similarity and prior | weights, restriction, cap, evidence for a nonzero weight | Approve the §3.3 weights (class 3, target kind 1, signals 2, dependency role 2, failure pattern 2), same host and environment profile only, cap 0.5, **default 0**; a nonzero weight needs the §3.5 comparison: at least 10 confirmed cases per class (*proposed here*; §3.5 sets no minimum), 5 trials, no accuracy regression, hard checks 0, reviewed; confirm that no automatic weight update is authorized | The defaults are already interpretable and bounded; with the prior at 0 nothing changes until labels exist and the comparison is reviewed. |
| 6 | Application slices | order and gates | (1) tables, use cases and insert-only grants with SQLite/Postgres tests, no route; (2) the deterministic verifier with durable delivery through a new outbox-style loop in the worker (the §11 `notification_outbox` pattern, not built yet; the worker runs only the intake-claim and lease-renewal loops today); (3) `confirmed_only` recall, default `true` (returns nothing until labels exist); (4) the route only after ACR-0018's deployment gates (WebAuthn, step-up, privileged path) are met on the deployed profile; (5) the offline exporter to a declared regression set, never `tests/eval/heldout/`; (6) the prior stays 0 until item 5's comparison | Each slice is safe on its own and reversible; nothing a human can write exists before the access gates; durable delivery must be proved before deployment (§3.1), so slice 2 includes building and testing that loop. |
