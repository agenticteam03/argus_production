# ACR-0031 — Replay every dependency probe transition after delayed ticks or restarts

This extends [ACR-0025](ACR-0025-live-dependency-graph.md). The dashboard and incident read continue to use the same
link-state rules and the exporter remains the only probe source.

| Field | Value |
|---|---|
| Status | `accepted` (2026-10-24) |
| Proposed by | conantkd (+ agent) · 2026-10-24 |
| Accepted by | conantkd · 2026-10-24 |
| Second approval (safety principle only) | not required; no safety principle changes |
| Architecture version | 1.8.35 → 1.8.36 (1.8.35 is PR #314, merged first) |
| Task / PR | [T-0046](../../tasks/current/T-0046-live-dependency-graph.md) · one PR for L5 temporal recovery and L6 |

## 1. Detect and explain

The scheduler's 60-second reconcile tick reads one instant probe sample and records the state at the time the scheduler
ran. A fault that starts and recovers between ticks is absent from `link_event`, and an outage in the scheduler or its
connection to Prometheus leaves an unprocessed interval. The L6 deterministic baseline also needs an explicit read of
the registered link history when it investigates dependency, health-check and gateway incidents.

## 2. Why the current architecture is insufficient

ACR-0025 §3.1 and the applied §7.3 specify an instant `dependency_probes(owner)` read once per tick. That read cannot
recover transitions the tick did not observe, and its evaluated timestamp does not identify the exporter's source
sample. A durable event table alone cannot tell the next tick which samples it has already processed.

## 3. Smallest reasonable change

The scheduler reads distinct source samples from `MetricsPort.dependency_probe_history(owner, cursor, now)`, a bounded
Prometheus range query with a five-second evaluation step over the exporter's existing 15-second scrape series. It pairs
each value with Prometheus `timestamp(series)` so scheduler evaluation time is never recorded as probe time. Repeated
evaluations of one scrape collapse to one source sample. Each owner's cursor is persisted in `link_probe_cursor`. A
replay query is capped at four hours; if a cursor is older, the state is rebased to `unknown` at the beginning of the
retained window before newer samples are replayed. This bounds Prometheus work and makes the unobserved gap explicit.
Writing a state transition, its chained `link.changed` audit row, and advancing that cursor is one transaction; an
unchanged state advances the cursor without adding an event. A host whose Prometheus cannot be read is skipped without
advancing its cursor, so the next successful tick can replay the retained interval. A fresh read with a gap beyond the
configured sample staleness records `unknown` at the staleness boundary. While a link is `unknown` and its exporter
sends nothing, its cursor moves up to the staleness limit before `now` without a row, so each window stays one tick
plus the staleness limit long instead of growing to four hours.

The cursor table lives with Argus application state in Postgres on **vm-095** (and in the local SQLite store). Probe
samples continue to come from the target's own Prometheus on **vm-166**; no storage expansion or new probe is made on
the monitoring VM.

L6 offers `network.link_states` only to `dependency_unavailable`, `health_check_failed` and
`nginx_upstream_failure`. The deterministic baselines explicitly read and use that evidence. Five replay cases cover
SC-03, SC-07, health-check failure due to a broken dependency, and SC-08 with a broken or slow upstream link; each fails
without the offer and passes with it. The offer is measured with the deterministic baseline only (control 57/66,
treatment 62/66, hard checks 0); `health_check_failed` is a `model_loop` class, and a model arm is not measured yet. In
SC-03, SC-07 and the health case the read changes the root cause; in the SC-08 cases it changes the mechanism (a broken
or slow link), not the root cause.

**Alternatives considered:**
- A: reduce the scheduler interval below the exporter scrape interval. Rejected: it still cannot recover ticks lost to
  a restart or a Prometheus outage, and does more polling without a durable checkpoint.
- B: store every exporter sample in Argus. Rejected: the seven-day Prometheus range is sufficient for replay; Argus only
  needs transitions and a cursor.
- C: leave the architecture unchanged and keep the instant read. Rejected: the red regression test reproduces the missed
  `ok → broken → ok` interval and a restart can replay rows.

## 4. Consequences

- **Code:** `MetricsPort`; Prometheus range adapter; scheduler transition recorder; SQLite and Postgres stores; migration
  014 and `argus db check`; three detector class tags and baseline strategy; replay fixture support.
- **Tests:** historical samples retain source timestamps; repeated range evaluations collapse; failures do not advance a
  cursor; restart resumes without duplicate transitions; transaction and cursor permissions are tested; both staleness
  boundaries, an older probe refused by the store and a silent exporter's short window are tested; five evaluation
  scenarios consume the read and fail without it.
- **Deployment:** apply migration 014 on vm-095 before the new image. No change on vm-166. Run the existing SC-03 and
  SC-07 checks after the developer executes the prepared VM block.
- **Risk:** six bounded Prometheus range requests per owner per scheduler tick, at most a four-hour range (only while
  replaying a backlog; a silent exporter keeps the window at one tick plus the staleness limit). Each request
  keeps the existing timeout and host isolation. The additive cursor table is safe to leave empty when rolling
  application code back.
- **How to reverse it:** disable `link_states.enabled` and redeploy the previous image; keep migration 014 and its empty
  or last-used additive cursor table (forward-only migration policy).
- **Safety principle touched:** no. The probe stays read-only and unchanged, the cursor and events remain within the
  existing audit boundary, host isolation is retained, and the write gate is unchanged.

## 5. Decision

Accepted by `conantkd` on 2026-10-24 after choosing range replay with a durable per-link cursor. The monitoring VM remains
the sample source; the cursor is Argus state on vm-095.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version 1.8.36, changelog line added
- [x] journal entry
- [x] this ACR, the architecture change and the first code that needs it are in the same pull request
