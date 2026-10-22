## 2026-10-22 — T-0048: proposed answers to ACR-0029's six acceptance decisions

Type: proposal (documentation only)
Who: juanbetancurm (+ agent); review: conantkd
Context: ACR-0029 (#269) was merged as `proposed`; its §5 lists six decisions the team must take before acceptance,
and #270 carries them as open points. A short memo makes that discussion faster.
Decision / result:
- T-0048 gains a section "Acceptance decisions (proposed answers)": for each decision the options, a recommendation
  and the reason, citing the ACR.
- Recommendations: keep ACR-0018's `feedback` grant with a second operator for contradicting production labels;
  step-up on every write; reuse existing freshness bounds with a 30-min stability window and a 7-day recurrence rule
  (OD-7 starting values); retention at least as long as episodic state, never pruning cited evidence; approve the
  similarity weights with the prior at 0 until a reviewed comparison; six reversible application slices with the
  route last, after ACR-0018's deployment gates.
Consequences: no ACR status change, no architecture or code change. The team accepts or changes these answers in the
acceptance PR.
References: [T-0048](../../tasks/current/T-0048-incident-feedback.md),
[ACR-0029](../../architecture/changes/ACR-0029-incident-feedback.md).

### Test state

Documentation only; no runtime change. Full offline suite on main `096bf90` plus this memo: passed, 0 failed
(1554 collected, only the known detached-CI Brain test deselected). Brain lint and audit clean. Peer pre-review
(S3): four findings, all applied.
