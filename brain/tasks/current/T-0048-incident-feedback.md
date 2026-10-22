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
