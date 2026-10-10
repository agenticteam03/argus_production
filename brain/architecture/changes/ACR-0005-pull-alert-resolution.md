# ACR-0005 — Alert resolution in a pull profile, and what a resolution does to the incident

| Field | Value |
|---|---|
| Status | `accepted` → applied in the same pull request |
| Proposed by | `conantkd` (+ agent) · 2026-10-09 |
| Accepted by | `conantkd` · 2026-10-09 |
| Second approval (safety principle only) | not needed (no safety principle is touched) |
| Architecture version | from `1.8.4` → `1.8.5` |
| Task / PR | T-0026 · PR to be opened |

## 1. Detect and explain
T-0026 implements §6.4 "Resolution". This deployment is `restricted-ssh` (ACR-0003): alerts are **pulled**
(`ReconcileFiringAlerts`, §7.3) and no Alertmanager pushes to Argus, so Argus never receives a `resolved`
notification. The Alertmanager API v2 only lists active alerts: a resolved alert simply stops being listed. Without a
rule for that absence, no occurrence would ever be resolved in this deployment.

## 2. Why the current architecture is insufficient
§6.4 "Resolution" says *"a `resolved` notification marks only that fingerprint resolved"* and *"An incident may close
from alert resolution only when all attached fingerprints are resolved and no write or verification is in flight"*.
§7.3 describes only how firing alerts are pulled. Two things are missing: (1) how a pull profile learns that an alert
resolved, (2) what happens to an incident in each state (queued, running, concluded) when its alerts all resolve:
"may close" leaves it open, and §16 keeps a concluded incident forward-only.

## 3. Smallest reasonable change
§6.4 "Resolution", after the existing text, add:

> In a pull profile (§7.3) an occurrence is resolved when its alert is **absent from a successful read of its host's
> active alerts** (`AlertSourcePort.active_alerts(host)`: silenced and inhibited alerts are still active), and only
> occurrences recorded before that read are judged by it. A host that cannot be read resolves nothing (unknown is
> never healthy). When the last occurrence of an incident resolves: a **queued** incident (no worker has claimed it)
> closes with `resolved_externally` and no run; a **running** incident finishes its diagnosis (in a read-only release
> no write or verification is ever in flight); a **concluded** incident is not changed. Each resolution is audited
> (`incident.alert_resolved`, `incident.alerts_all_resolved`).

§7.3: `ReconcileFiringAlerts`, after submitting a host's firing alerts, reads its active alerts and resolves the
host's occurrences that are absent. §8.1: `AlertSourcePort` gains `active_alerts(host)`.

**Alternatives considered:**
- A: **resolution only from the push webhook.** Why not: this deployment has no push; nothing would ever resolve.
- B: **absence from the firing read** (`silenced=false&inhibited=false`). Why not: silencing an alert during a
  maintenance would mark it resolved and could close its incident. A second read with every active alert costs one
  small HTTP request per host per pass.
- C: **cancel a running investigation** when its alerts all resolve. Why not: there is nothing unsafe to stop in a
  read-only release, the diagnosis still explains what happened, and it needs the cooperative cancel of OP-009
  (unmerged).

## 4. Consequences
- Code: `application/alerts.py` (`resolve`, `resolve_absent`, the reconciliation), `adapters/outbound/
  alerts_alertmanager.py` (`active_alerts`), `ports.py`, the stores (`resolve_alert_occurrence`,
  `firing_occurrences`, `close_queued_incident`), the webhook (`endsAt`), `IncidentOutcome.resolved_externally`.
- Schema: migration 005 adds `alert_occurrence.resolved_at`; the runtime role gets `UPDATE (status, resolved_at)`,
  forward only (`firing → resolved`, a trigger refuses anything else); still no DELETE. `argus db check` proves it.
- Risk: an Alertmanager that loses its state (restart without its data volume) lists nothing for a moment, and every
  occurrence of that host is resolved although the condition goes on. The alert fires again with a new `startsAt`, so
  the next pass records it again (a new incident if the previous one concluded). The read must succeed; an empty
  answer from a reachable Alertmanager is trusted.
- How to reverse it: drop the resolution call from `ReconcileFiringAlerts` and `HandleAlertNotification`; the column
  and the grant can stay (older code ignores them).
- Does it touch a **safety principle** (read-only, write gate, host isolation, evidence integrity, secrets)? **No.**
  Evidence and audit stay insert-only; the occurrence's identity, incident and labels cannot change.

## 5. Decision
`conantkd`, 2026-10-09, chose absence from a successful read of every active alert (silenced included), and closing
only a queued incident (a running one finishes, a concluded one is not changed), over webhook-only resolution and over
cancelling a running investigation.

## 6. Applied
- [x] `ARCHITECTURE.md` updated, version bumped, changelog line added (with this ACR's link)
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request
