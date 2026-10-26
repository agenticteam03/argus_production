# PHASE-18 — Supervised remediation against a fake gateway

| Field | Value |
|---|---|
| Status | `in review` — PR [#323](https://github.com/agenticteam03/argus_production/pull/323) is ready for review; `test` and `frontend` CI passed on the implementation head. Stacked on #318 pending #316; [test evidence](../../journal/entries/2026-10-25-T-0051-phase18-supervised-actions.md) |
| Phase | 18 of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md) |
| Architecture | [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), accepted; §14 designed, not yet built on main |
| Branch | `task/T-0051-supervised-actions`, stacked on #318 and current #316 until those PRs reach main |
| Owner | `conantkd` (+ agent); teammate review required for protected action/architecture/migration paths |
| VM lease | none for offline code and fake-gateway tests; a later deployment requires both leases |

## Goal

Build the §14 proposal, judge, approval, hold, action ledger, recovery and verification machinery against a fake
gateway. Keep `write_gate.open: []`, with no real gateway route, credential or action release. No approval HTTP route is
added in this phase. Phase 19 handles access/UI/gateway; phase 20 releases the first lab pair in a separate PR.

## Steps and exit proof

1. Freeze a proposal with the target identity, arguments, cited evidence and grounds, prediction, alternatives,
   preview, rollback, policy/inventory/evidence versions and expiry. Hash the full canonical payload. Missing grounds
   become a non-executable suggestion; a model-only claim never becomes an executable proposal.
2. Review the frozen package with a separate judge model. The judge sees no first-model conversation and has no tools.
   Validate the fixed output schema; timeout or invalid output is `doubt`; risk never decreases.
3. Persist insert-only proposals and forward-only approval, outbox, resume intent, action, hold and action-outcome
   records in migration 015 and SQLite. The runtime role has only the necessary grants. `argus db check` proves the
   positive writes before refusal checks. Answer + resume intent and approval + outbox are atomic.
4. Build the LangGraph pause/resume path and deterministic precheck. Require a current, digest-bound human answer,
   unchanged target identity and reviewed versions, a live incident, fresh compatible evidence, no hold, and the
   closed gate check. No model output may reach dispatch.
5. Dispatch only to a journaled fake gateway. Persist `attempting` before the call. Reconcile by action ID after
   ambiguous failures; never blindly send a second action. Verify with a sample newer than completion and compare
   the prediction before recording `recovered_verified`.
6. Run binding, crash-point, hold, prompt-injection and fake-gateway tests, then the full offline and PostgreSQL
   suites and exact-head CI. Keep the write-gate standing test green.

## Judge model comparison (internal decision record)

The deployed deciding-model default in `argus/infrastructure/wiring.py` is `gpt-5.6-luna` unless the VM overrides
`ARGUS_LLM_MODEL`. The judge must be a **different** model. Official OpenAI documentation lists `gpt-6-luna` as the
efficient candidate, `gpt-6.1-sol` as the balanced candidate and `gpt-6-astra` as the strongest reference. All three
are candidates: [model catalog](https://developers.openai.com/api/docs/models),
[model-selection guide](https://developers.openai.com/api/docs/guides/model-selection),
[evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

| Judge candidate | Standard input/output per 1M tokens (2026-10-25) | Internal assessment |
|---|---:|---|
| `gpt-6-luna` | $0.10 / $0.50 | Lowest cost and latency candidate; test carefully for harmful false agreement. |
| `gpt-6.1-sol` | $2 / $10 | **Provisional choice**: separate from the default decider and stronger review budget at moderate cost. |
| `gpt-6-astra` | $10 / $50 | Strong reference for difficult and trap cases; expensive as the routine judge. |

Prices are from [official Standard pricing](https://developers.openai.com/api/docs/pricing) at short context, before
regional or processing-tier adjustments. At the stated token caps, the upper-bound uncached Standard costs would be
about $0.03, $0.60 and $3.00 respectively if **each** model consumed the entire 150k input/30k output budget;
the actual comparison shares that budget, so these figures are not a bill or measured use. `gpt-6.1-sol` is selected
only for offline adapter wiring; the release choice remains provisional until the labeled comparison is run.

Before a model choice, run the same human-labeled package through each candidate on good, bad and trap proposals.
Record model/reasoning settings, schema-valid rate, harmful false-agree count, good-proposal agree rate, `doubt` on
missing evidence, median/p95 latency, input/output tokens and billed cost. A harmful false agree fails the gate; no
winner is selected by cost alone. The preregistered initial budget is 18 cases (6 per group), two repetitions, three
models, at most 150,000 input and 30,000 output tokens or USD 10 total. These are caps, not claimed usage.
The reproducible case manifest and budgeted runner are in `ops/phase18_judge_eval.py`. Run
`python -m ops.phase18_judge_eval` to inspect the 18-case dry run. The paid run requires an explicit `--live`,
`OPENAI_API_KEY` and `--output` outside the repository; this checkout has no key, so no live metric or winner is
claimed. The harness does not send raw case text to the result file; it stores only case IDs and measured metrics.
Availability and prices must be rechecked at execution against the connected API account and
[official pricing](https://developers.openai.com/api/docs/pricing); no credential or secret is stored in this task.

## Dependencies and release boundary

- #316 supplies the Phase 17 catalogue and cards; #318 forbids candidates on vm-095. This branch contains both
  while they are reviewed, but neither is claimed merged on main.
- ACR-0018 phase 16 exit proof and the off-host audit digest are prerequisites for phase 19 and any real approval or
  gateway route. #314 remains in review. Phase 18 requires neither a VM mutation nor an open write gate.
- The first real action is `container.start` only for `vm-166/container:argus-lab-cache`, with its own release PR,
  two reviewers and all §22.2 checks. This task never opens that pair.
