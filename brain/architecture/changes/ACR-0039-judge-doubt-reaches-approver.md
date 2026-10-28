# ACR-0039 — A judge's doubt reaches the approver

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | `conantkd` · 2026-10-28 |
| Accepted by | `conantkd` · 2026-10-28 |
| Second approval (safety principle only) | not required |
| Architecture version | proposed: `1.8.46` → `1.8.47` |
| Task / PR | demo of 2026-10-28 · PR to be numbered on opening |

## 1. Problem

ACR-0019 §3.8 designed the judge to make things stricter: it "raises the colour, and shows its reasons to the approver. It never approves or changes the proposal." The phase 18 reading (T-0051) went further: a `doubt` or `disagree` stops the proposal before any approval request, and the request, the answer, the executor and the database (migration 016) all refuse without a stored `agree`.

In practice the judge answers `doubt` on almost every proposal. On 2026-10-28 every verdict of the S1 and S4 rehearsals was `doubt`, with `cause_supported`, `action_addresses_cause` and `grounds_support_action` true but `risk_understated` true: it wants stronger verification than the card states. So no action ever reaches a person, although the diagnosis is right and a person would decide with the same reasons in front of them.

## 2. Why the current architecture is insufficient

A stop on `doubt` turns a second opinion into a veto that no person can see past. The design's own answer, showing the reasons and the raised colour to the human who is accountable for the decision, is not available.

## 3. Smallest reasonable change

- A `doubt` reaches the approver. Only a `disagree`, a forbidden colour, a verdict for another digest or no verdict at all stops a proposal before an approval (`approvable_verdict`, `APPROVABLE_VERDICTS = {agree, doubt}`).
- A `doubt` raises the colour one level, like a `disagree` does (`judge_proposal`, including an invalid judge answer). A doubt that makes the colour red keeps the typed host-qualified target. A review that cannot start still stores a red `doubt` and stops (the graph treats the error as held back).
- The same rule in every place that checks it: the approval request and its answer (`OfflineActionPath`), the private answer route (`answerable_approval`), the executor before dispatch (`ActionExecutor._frozen`), and the database: migration 018 replaces migration 016's trigger function so an approval row may follow an `agree` or a `doubt` on the exact digest without a forbidden colour; SQLite mirrors it with renamed triggers (an older file's agree-only triggers are dropped at start); `argus db check` proves a doubt is accepted and a disagreement refused.
- The person is told:
  - the approval notice adds "The independent judge doubted it." (no other detail, ACR-0018 §18);
  - the pending list marks it "Judge doubted";
  - the approval card shows a warning that the judge doubted the action, that the person decides, and the raised colour, above the judge's reasons;
  - the graph audits `judge.doubt_sent_to_approver` with the colour, and the answer's `action.approval_answered` records `judge_verdict` and `risk`.

**Alternatives considered:**

- Keep the stop and tune the judge's prompt or the cards: still worth doing (the judge's reasons show what the cards miss), but measured over several runs, not before the demo.
- Let a `disagree` through as well: rejected; a disagreement names a wrong cause or a less invasive alternative, which a person should not have to catch alone.

## 4. Consequences

- Code and tests: `argus/actions/remediation.py`, `argus/actions/execution.py`, `argus/orchestration/action_path.py`, `argus/orchestration/graph_runner.py`, `argus/application/approval_view.py`, `argus/adapters/inbound/http.py`, `argus/adapters/outbound/sqlite_store.py`, `argus/adapters/outbound/postgres_store.py`; `deploy/migrations/018_approval_accepts_doubt.sql`; `ApprovalCard.jsx`, `PendingApprovals.jsx`; their tests.
- Deployment, in this order on vm-095 with the lease: a backup, `sudo bash ops/db-migrate.sh` (018), the new image of the agent, worker and scheduler and the UI, then `argus db check`. The old image keeps working on the new schema (it still refuses a doubt in code); the new image needs migration 018 or the database refuses the approval row.
- Risk: more proposals reach a person, some of them doubted. The person still needs the private path, two security keys and a step-up bound to the exact digest; the colour is higher; the precheck still re-reads the target; the write gate still names each released pair. The judge's agreement with human decisions becomes measurable on doubted proposals.
- Reversal: a migration that restores the agree-only function, and `APPROVABLE_VERDICTS = {agree}`.
- Safety principle changed: no. The human approval with a step-up is the final gate (ACR-0019 §3.10); this returns the judge to ACR-0019 §3.8's own design, where it raises the colour and shows its reasons.

## 5. Decision

`conantkd` asked for it on 2026-10-28: when the judge is in doubt, the action still goes to the person, who sees that it is in doubt and the action's risk.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped to 1.8.47, changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the code that needs it are in the same pull request
