# T-0048 — Memory and feedback: was the diagnosis right, and what fixed it

| Field | Value |
|---|---|
| Status | `proposed` — [ACR-0029](../../architecture/changes/ACR-0029-incident-feedback.md) drafted; acceptance and phase 16's required access/audit deployment gates pending; no implementation |
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
- `POST /api/v1/incidents/{id}/feedback`: human only, a `feedback` permission, step-up when it labels a cause (ACR-0018).
- `knowledge.prior_incidents` gains `confirmed_only`; a failed fix is never a precedent for that fix.
- Case similarity (`incident_features`, an interpretable weighted match) and a prior for the T-0047 ranking.
- An offline export of a confirmed incident to a draft evaluation case, reviewed in a PR, never automatic.

## Why it waits

Labels steer future diagnoses, so they are privileged writes: they need the per-person accounts, step-up and audit of
ACR-0018 first. Until then, T-0047 ranks with evidence weights only.

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
