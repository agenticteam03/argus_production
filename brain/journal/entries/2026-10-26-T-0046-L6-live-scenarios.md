## 2026-10-26 - T-0046 L6: SC-03 and SC-07 live on main 16028c7

Type: verification
Who: conantkd (+ agent)
Context: #322 (probe history replay, `network.link_states` offered to three classes) deployed in DEPLOY-16028c7; its
next step was a live SC-03/SC-07 check. Both leases.
Decision / result:
- SC-03 and SC-07 PASS once each (baseline, no model call); both incidents read `network.link_states`; SC-07's
  diagnosis cites the recorded broken link `client -> backend`.
- The scheduler kept a 15 s `api -> cache` `broken`/`ok` transition between two ticks at its source times, and marked
  `client -> backend` `unknown` exactly 90 s after its last sample.
Consequences: T-0046 L6's live check is done. The model arm (`health_check_failed`) stays unmeasured until the replay's
`now` is pinned (ACR-0031).
References: [evidence](../../execution/history/T-0046-l6/step-03/evidence.md), #322, DEPLOY-16028c7.

### Test state

Live: SC-03 1/1 PASS, SC-07 1/1 PASS; link rows as described; `LAB BASELINE OK`.

### Next step

T-0046: the model arm once the replay's `now` is pinned; otherwise L6 is complete.
