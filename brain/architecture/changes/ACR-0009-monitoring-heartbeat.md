# ACR-0009 — A monitoring heartbeat per host: Argus notices when it stops seeing a host, and resolves nothing meanwhile

| Field | Value |
|---|---|
| Status | `accepted` (#108, `juanbetancurm`, 2026-10-12); applied in T-0035 (ARCHITECTURE.md 1.8.8, code) |
| Proposed by | `conantkd` (+ agent) · 2026-10-12 |
| Accepted by | `juanbetancurm` · 2026-10-12 (approval of #108) |
| Second approval (safety principle only) | not needed (no safety principle is touched; see §4) |
| Architecture version | from `1.8.7` → `1.8.8` (with the implementation) |
| Task / PR | T-0035 (Phase 13: "Prometheus down on one host", T-0032's "not covered") · PR to be opened |

## 1. Detect and explain

T-0032 (2026-10-10) stopped vm-095's Prometheus for about 2 minutes: an investigation **asked for** on vm-095 ended
`UNDIAGNOSABLE` and vm-166 stayed `HEALTHY`, as designed. Its record lists what is not covered: **nothing tells anyone
that a host's monitoring stopped**. Two consequences, both in the current code:

1. **Silence looks like health.** Argus opens incidents from the alerts it pulls (`ReconcileFiringAlerts`, §7.3). With
   the host's Prometheus down, no alert is evaluated, none reaches its Alertmanager, and Argus opens nothing for that
   host: from outside, the host looks healthy while its containers may be failing.
2. **False resolutions.** When a host's Prometheus stops but its Alertmanager still answers, the active alerts expire
   at their `endsAt` (about 4 minutes: Prometheus sends `endsAt = now + 4 × max(evaluation_interval, resend_delay)`).
   They disappear from `GET /api/v2/alerts`, and `resolve_absent` (§6.4 "Resolution", ACR-0005) marks the host's
   occurrences resolved and closes queued incidents `resolved_externally`, a resolution that never happened. ACR-0005
   protects only the case where the Alertmanager cannot be read ("a host that cannot be read resolves nothing").

## 2. Why the current architecture is insufficient

- §7.3: `ReconcileFiringAlerts` reads each host's firing and active alerts; nothing checks that the host's alert
  pipeline is **alive**, only what it currently lists.
- §6.4 "Resolution" (ACR-0005): *"an occurrence is resolved when its alert is absent from a successful read of its
  host's active alerts"*. A successful read of an Alertmanager whose Prometheus is dead is not evidence that the alerts
  stopped: the absence is unknown, and §9 / G-007 say unknown is never healthy.
- §2 (classes): `monitoring_blind_spot` (RB-014) covers a scrape target down **as seen by a working Prometheus**
  (T-0027). It cannot fire when the Prometheus itself, or its Alertmanager, is what stopped.

## 3. Smallest reasonable change

**Name.** The condition is **"host monitoring unavailable"** (`monitoring_unavailable` in records): a missing
heartbeat can come from Prometheus, Alertmanager or the transport between them and Argus. "Prometheus down" is one
cause, to be confirmed.

**§4.1 / `deploy/monitoring/alerts.yml`** — add one always-firing rule, the same on every host (the label comes from
the host's own series):

```yaml
- alert: ArgusMonitoringHeartbeat      # ACR-0009: always firing while this Prometheus evaluates rules
  expr: count by (argus_host) (up{argus_host!=""}) > 0
  annotations: {summary: "monitoring heartbeat of {{ $labels.argus_host }}"}
```

**§7.3** — after the existing text, add:

> **Monitoring heartbeat (ACR-0009).** On every reconcile tick, for each host, Argus checks the host's
> `ArgusMonitoringHeartbeat` alert in the active alerts it already reads (`active_alerts(host)`: silenced and
> inhibited included, so a silence never hides a loss). The heartbeat is **fresh** when it is listed with its
> `argus_host`, its `endsAt` is in the future, and its `updatedAt` is no older than `stale_after` (default 3 minutes;
> Prometheus re-sends every `resend_delay`, 1 minute by default). An alert that is still listed but no longer renewed
> is **not** fresh: reading a kept copy again is not a new heartbeat.
>
> - **Lost:** no fresh heartbeat for `stale_after`, or never one since the host was configured or the scheduler
>   started plus a grace period (default 5 minutes). Argus opens **one incident per host and loss episode** on the
>   host target (`host/host:host`), class `monitoring_blind_spot`, RB-014, finding *"Host monitoring unavailable"*,
>   with a cause from what it observed (table below), and closes it at once as `undiagnosable`, escalated: **no
>   worker run, no model call, no read of the host** (a run would read metrics that may still answer and could end
>   "healthy"). Its idempotency key is `monitoring:<host>:<episode start>`.
> - **Recovered:** two consecutive ticks with a fresh heartbeat. Argus audits `monitoring.recovered` on the episode's
>   incident. This confirms the monitoring is back, not that the host's applications are healthy.
> - **Bounded Prometheus check:** when the heartbeat is lost, Argus also makes one bounded read of the host's own
>   Prometheus (`GET /-/ready`, 3 s timeout, read-only) to refine the cause; it never restarts anything.
>
> | Observation | What Argus records |
> |---|---|
> | Alertmanager answers, heartbeat fresh | monitoring alive (no record per tick; transitions only) |
> | Alertmanager answers, heartbeat missing or stale | heartbeat lost: check the host's Prometheus rule evaluation and alert delivery |
> | Alertmanager does not answer | monitoring cannot be read: check the host's Alertmanager and the transport |
> | and Prometheus does not answer the bounded check | Prometheus not reachable from Argus: cause to be confirmed |
>
> The heartbeat alert never reaches `HandleAlertNotification` (it is filtered out by its `alertname` before intake)
> and never opens an investigation.

**§6.4 "Resolution"** — after the ACR-0005 text, add:

> A host whose monitoring is **lost** (ACR-0009) resolves nothing: while its heartbeat is not fresh, the absence of
> its alerts is unknown, not a resolution. Its occurrences stay `firing` until the monitoring has recovered and a
> later read shows them absent.

**Persistent state (new migration).** One row per host — state (`alive` | `lost`), the episode start, the last
`updatedAt` seen, the consecutive fresh ticks, the episode's incident, an optional maintenance window — so a
scheduler restart neither opens a second incident for the same episode nor forgets one.

**Maintenance (explicit).** A planned stop is declared, never inferred from an Alertmanager silence (the heartbeat
check ignores silences on purpose): `argus monitoring maintenance <host> --minutes N --as <who>`, N at most 240,
audited, stored with its end. During it a loss is audited (`monitoring.lost_in_maintenance`) but opens no incident;
the resolution rule above still applies. After it ends, a loss still present opens its incident.

**Not covered (stated):** Argus itself runs on vm-095; if vm-095 as a whole is down, nothing reports it. This watches
each host's monitoring from Argus, not Argus.

**Alternatives considered:**
- A: **cross-host watching** (each host's Prometheus scrapes the other's and alerts on it). Why not: new traffic and
  credentials between the hosts, against the per-host isolation of the monitoring (§4.1, ACR-0003); and the alert
  would still arrive through a pipeline that could be the broken one.
- B: **query each Prometheus directly on every tick** (`up`, or `/-/ready`). Why not as the main signal: it proves the
  server answers, not that rules are evaluated and alerts delivered, which is what incident intake depends on. It is
  kept as the bounded check that refines the cause.
- C: **keep the architecture and rely on investigations ending `undiagnosable`** (T-0032). Why not: nobody asks for an
  investigation when nothing alerts, and the false resolutions of §1.2 stay.
- D: **a new incident class `monitoring_unavailable`**. Why not: `monitoring_blind_spot` and RB-014 already describe a
  loss of visibility; a new class would need its own registry entry, runbook and evaluation cases for the same
  escalation.

## 4. Consequences

- **Code:** `deploy/monitoring/alerts.yml` (the rule); `AlertNotification` gains `updated_at` (the adapter reads
  `updatedAt`); a heartbeat check in the reconcile tick (`application/`); `resolve_absent` skipped for a lost host;
  the heartbeat filtered out before intake; one migration (state per host) in both stores; a CLI command for
  maintenance; a bounded readiness read of the host's Prometheus (an adapter method).
- **Tests:** fresh / stale (listed but not renewed) / missing / never seen within and after the grace; Alertmanager
  unreachable; one incident per episode across a scheduler restart; recovery after two fresh ticks; no resolution
  while lost; silenced heartbeat still checked; maintenance opens nothing and expires; the heartbeat never reaches
  intake; no model call and no worker run.
- **Deployment:** both hosts' Prometheus reload the rule; vm-095's scheduler and agent rebuilt; the migration.
  Verification with both leases: stop vm-166's Prometheus (as T-0032), then separately its Alertmanager; expect one
  incident per episode, application incidents of that host not closed, recovery after two ticks; the other host
  unaffected; NO INTERFERENCE.
- **Timing:** detection within about `stale_after` + one tick (≈ 4 minutes with the defaults; target ≤ 5); the
  defaults are adjusted after measuring the deployed versions' `updatedAt` renewal and `endsAt`.
- **Risk:** a wrong `stale_after` gives false losses (too short) or late ones (too long); mitigated by the
  measurement above and by the two-tick recovery. A wrong host label is impossible to mistake for another host: an
  alert whose `argus_host` is not the host read is already dropped (§7.3).
- **How to reverse it:** remove the rule, disable the check (configuration), keep the migration (it only adds a
  table); resolution falls back to ACR-0005 as written.
- **Safety principle?** No: read-only (one more alert read, one bounded readiness read; nothing restarted), the write
  gate stays closed, host isolation is kept (each host's heartbeat is read from its own Alertmanager and must carry
  its own `argus_host`), evidence integrity is strengthened (no resolution recorded without evidence), no secret.

## 5. Decision

Proposed by `conantkd` on 2026-10-12, from a design discussed with the agent: a per-host heartbeat through the alert
path Argus already pulls, judged by renewal and not by presence; a deterministic, immediately escalated incident per
loss episode (no model, no run); no resolution of that host's alerts while its monitoring is lost; explicit,
time-bounded maintenance. Waiting for a teammate's acceptance in this pull request; the implementation (T-0035)
follows in its own pull request, which applies this ACR to `ARCHITECTURE.md`.

## 6. Applied

- [x] `ARCHITECTURE.md` updated (§6.4, §7.3; the rule in `deploy/monitoring/alerts.yml`), version 1.8.8, changelog line (T-0035)
- [x] journal entry (`journal/entries/2026-10-12-ACR-0009.md`)
- [x] the architecture change and the first code that needs it in the same pull request (T-0035)
