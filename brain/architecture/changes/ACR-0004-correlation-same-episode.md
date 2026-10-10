# ACR-0004 — Correlation: an alert of the same episode joins the incident that already concluded

| Field | Value |
|---|---|
| Status | `accepted` → applied in the same pull request |
| Proposed by | `conantkd` (+ agent) · 2026-10-09 |
| Accepted by | `conantkd` · 2026-10-09 |
| Second approval (safety principle only) | not needed (no safety principle is touched) |
| Architecture version | from `1.8.3` → `1.8.4` |
| Task / PR | OP-011 · PR #48 |

## 1. Detect and explain
OP-011 step 02 ([evidence](../../execution/history/OP-011/step-02/evidence.md)) deployed §6.4 as written. SC-03 on
vm-166 (the cache stopped) fired `DependencyProbeFailed` (startsAt 13:21:01) and `ContainerUnhealthy` (startsAt
13:21:31) on `argus-lab-api`. The scheduler pulled the first at 13:21:09; its incident `inc_67a608e63ce5` was
diagnosed and **closed at 13:21:40**, before the next pass (13:22:09) pulled the second alert. §6.4 attaches only to an
**open** incident, so the second alert opened `inc_e74b841c66f9`: the same class, the same root cause, twice the reads
and model cost. In this read-only phase an investigation often concludes in under a minute, faster than one pull
interval (60 s) or the spread between related alerts, so "open" is too narrow to catch one failure's alerts.

## 2. Why the current architecture is insufficient
§6.4 step 2: *"an open incident with the same target and incident class whose `last_evidence_at` is within
`CORRELATION_WINDOW` and which passes the compatibility test → attach"*. Step 3 then creates a new incident. An alert
whose condition **began while the incident was still being investigated** belongs to the same episode, but is treated
as a new failure as soon as the incident has concluded.

## 3. Smallest reasonable change
§6.4, before:

> 2. otherwise, an open incident with the same target and incident class **whose `last_evidence_at` is within
> `CORRELATION_WINDOW`** *(default 30 min)* **and which passes the compatibility test** → attach;
> 3. otherwise, create a new incident.

After:

> 2. otherwise, an open incident with the same target and incident class **whose `last_evidence_at` is within
> `CORRELATION_WINDOW`** *(default 30 min)* **and which passes the compatibility test** → attach;
> 3. otherwise, **the target's latest concluded incident (closed or escalated) of the same class, if the alert
> started (`startsAt`) at or before that incident's `closed_at`, the incident closed within `CORRELATION_WINDOW`, and
> the compatibility test passes** → attach (same episode). No investigation starts and the concluded incident is not
> reopened: the alert is recorded as an `attached` occurrence and the incident's evidence version grows. An alert that
> started after the incident closed is a recurrence and goes to step 4;
> 4. otherwise, create a new incident.

Plus a sentence under "Evidence version": the version of a concluded incident can grow by such late occurrences; a
consumer that needs the version a diagnosis used reads it from that run's state (§10), not from the incident.

**Alternatives considered:**
- A: **grouping wait** — the worker waits about one pull interval (+ margin, ~90 s) before starting an alert's
  incident, like Alertmanager's `group_wait`. Why not: it adds that latency to every alert, and still fails when two
  alerts are further apart than the wait.
- B: **keep §6.4** (open incidents only) and document the limit. Why not: OP-011's purpose (one failure, one answer)
  is not met in the lab's main multi-alert scenario.
- C: attach to any incident of the same target and class within the window, closed or not. Why not: a real recurrence
  (the cache stops again ten minutes after the diagnosis) would be swallowed by the old incident and never
  investigated. The `startsAt ≤ closed_at` rule separates the two cases by the alert's own timestamp.

## 4. Consequences
- Code: `application/correlation.py` (the concluded-incident rule), the stores (`latest_concluded_incident(target)`),
  tests in `tests/test_op011_correlation.py`. No schema change (migration 004 already holds the occurrences).
- Other sections: §6.4 only. §6.5 (scheduled requests) and the forward-only rule of a concluded incident (§16) are
  unchanged: the incident row is not updated.
- Risk: an independent failure of the same class on the same target whose alert started before the previous incident
  closed is attached instead of investigated. The compatibility test (labels naming no other container or
  dependency, the same class on a fresh snapshot) limits it; the occurrence and the audit event
  `incident.alert_attached` keep it visible.
- How to reverse it: remove step 3 (the concluded-incident rule) from `Correlator`; nothing persisted depends on it.
- Does it touch a **safety principle** (read-only, write gate, host isolation, evidence integrity, secrets)? **No.**

## 5. Decision
`conantkd`, 2026-10-09, chose this option over a grouping wait and over keeping §6.4: an alert that began during an
incident's investigation joins that incident even if it is pulled after the incident concluded; an alert that began
after it is a new incident.

## 6. Applied
- [x] `ARCHITECTURE.md` updated, version bumped, changelog line added (with this ACR's link)
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request
