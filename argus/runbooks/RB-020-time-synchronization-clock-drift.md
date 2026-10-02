# RB-020 — Time synchronization / clock drift

## Metadata

```yaml
id: RB-020
title: Time synchronization / clock drift
status: draft
owner: Argus Team
version: 1.0.0
created: 2026-09-29
last_reviewed: 2026-09-29
source_review_date: 2026-09-29
last_tested: null
detector: null
```

## Scope

Linux Host A/Host T and declared trusted time sources. Determine actual time service (chrony, systemd-timesyncd or another supported daemon), version and VM context. Chrony 4.6 is the reference version here, not an assumed deployment. Host A is not in the inspected lab target scope and needs explicit read authorization. [Common contracts](../RUNBOOK-CONVENTIONS.md) apply; clock detection/tools are missing.

## Incident definition

Clock offset/uncertainty exceeds the service's approved tolerance or synchronization is lost sufficiently to make event ordering/validity unreliable. A time zone display difference is not clock drift. Clock status must include source quality and measurement age, not just a “running” daemon flag. [chrony tracking](https://chrony-project.org/doc/4.6/chronyc.html)

## User / service impact

Possible TLS/authentication validity failures, misleading metric freshness, incorrect schedules and unreliable incident chronology. Corroborate the actual application failure; a time warning alone does not prove these impacts occurred.

## Trigger / detection conditions

Proposed alert: absolute offset plus reported uncertainty breaches the strictest relevant application tolerance over three fresh sync observations, or sync is lost beyond its allowed interval. Lab tolerance may be 1 second; production tolerance must be explicitly supplied. Unknown tolerance/source age is insufficient evidence. Required detector freshness remains fail-closed; never widen it to conceal drift.

## Symptoms

Clock-offset alert, unsynchronized status, old source update, inconsistent event order, certificate not-yet-valid/expired complaints, token time errors and apparent negative durations.

## Plausible causes / hypotheses

H1 time daemon stopped/misconfigured; H2 trusted source unreachable; H3 unreliable/wrong source; H4 VM pause/resume or manual step; H5 multiple competing time services; H6 log timezone/format issue; H7 source/application timestamp bug instead of host drift.

## Required evidence

Host/boot identity, active daemon/version, configured source IDs, selected source/reference time, measured offset/dispersion/delay and sync state/history, trusted comparison, monotonic observation sequence and relevant application errors. Preserve raw source times with uncertainty, not a falsely precise merged timeline.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_system_uptime()` | Target-host boot context; not synchronization proof | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Bounded application time-related errors | `READ_ONLY_SENSITIVE` |
| `correlate_incident_timeline(container, minutes=30)` | Existing timeline, trustworthy only after clock confidence is established | `READ_ONLY_SENSITIVE` |

Existing `get_journal_logs` permits only Docker/containerd and cannot inspect chrony/timesyncd. A denied unit is not grounds for arbitrary journal access.

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_time_sync_status(host_id)` returns daemon/source/offset/error bounds/reference time/boot identity via fixed read-only operations; `get_clock_offset_history(host_id, minutes)` returns drift/sync coverage; `get_time_service_logs(host_id, since, max_lines)` returns redacted allowlisted time-unit errors. Status/history are `READ_ONLY_SAFE`, logs `READ_ONLY_SENSITIVE`. Transport diagnosis must support the actual time protocol; a successful TCP check does not establish NTP reachability. No arbitrary date/chronyc/systemctl interface.

## Diagnostic workflow

| Step | Action / why | Interpretation / next step |
|---|---|---|
| 1 | Verify format/timezone versus a registered trusted reference | Equal instants displayed differently → H6. Real offset/unknown reference → 2. |
| 2 | Sync status with reference age/error bounds | Stopped service → H1; old/unselected sources → H2/H3; daemon active alone proves nothing. |
| 3 | Offset history and boot/VM change timeline | Sudden discontinuity supports H4; accumulating drift with source loss supports H2. Missing history leaves alternatives. |
| 4 | Approved time-unit config/logs | Conflicting service/config or source selection evidence → H1/H3/H5. Never retrieve secret auth material. |
| 5 | Compare actual application/metric timestamps | Host clock sound but one producer wrong → H7; avoid reordering unrelated incidents based on suspect times. |
| 6 | Owner plans safe synchronization repair | Step versus gradual correction requires application/cluster impact review. Current Argus cannot change time. |

## Decision tree

```text
timezone/format only? -> correct interpretation, not host clock
actual offset known with trusted reference? no -> insufficient_evidence
  yes -> daemon/source health -> config/network/source/VM investigation
         only one producer wrong? -> application timestamp defect
         unsafe to order events? -> mark temporal uncertainty, block dependent writes
```

## Evidence interpretation

Wall-clock time can jump; monotonic clocks provide a distinct elapsed-time basis and are not equivalent to globally comparable timestamps. [Linux clocks](https://man7.org/linux/man-pages/man2/clock_gettime.2.html) Chrony normally corrects gradually; a forced step can affect applications. Read-only tracking evidence is not authority to issue `makestep`. [chrony manual](https://chrony-project.org/doc/4.6/chronyc.html)

## False positives and edge cases

Timezones/daylight-saving display, stale reference, VM suspend, wrong clock domain, source uncertainty larger than observed offset, leap handling, container timestamps reflecting host clock and delayed log ingestion.

## Diagnosis outcome

All common outcomes allowed. Probable clock fault needs trustworthy comparison and daemon/source evidence; apparent event order or one TLS error alone yields multiple hypotheses. Explicitly reduce confidence in time-dependent diagnoses.

## Mitigation

Platform owner restores approved synchronization/source reachability and isolates time-sensitive automation through an existing operating procedure. Retain independent reference timestamps; do not falsify event times or alter auth tolerances.

## Recovery

Clock offset/uncertainty and source update age satisfy application tolerance, synchronization persists, and affected applications/metric freshness recover.

## Root-cause correction

Repair source/config/network/VM behavior, ensure one intended synchronization owner, and use correct elapsed-time clocks in software. systemd-timesyncd is one possible service, with its own documented behavior; do not assume chrony commands apply. [systemd-timesyncd source manual](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd-timesyncd.service.xml)

## Action safety

Time step, service/config/source changes are `MUTATING_HIGH_RISK` with host-wide blast radius. Require exact host/source/config, trusted offset evidence, database/lease/auth/scheduler owner review and plan for discontinuities. Block arbitrary Internet source, unauthenticated assumptions, unknown cluster impact, unsupported capability or a backwards-step proposal without explicit owner procedure. Current Argus remains read-only/escalating.

## Human-in-the-Loop

Show offset and error bounds, exact synchronization change, affected applications and time-dependent approval/audit risk. Approval to restart a container is never approval to set host time; stale clock confidence can also invalidate action expiry checks.

## Forbidden actions

`FORBIDDEN`: arbitrary set-date/makestep, turn off TLS/token validity checks, forge timestamps, alter time to extend approvals, unreviewed source trust or silently merge events with uncertain ordering.

## Evidence preservation

Retain original source/collection timestamps, clock domain, boot ID, offset bounds and event sequence before correction. Store append-only evidence; never rewrite prior audit times to make them appear ordered.

## Verification

After owner repair, at least three fresh sync updates spanning 5 minutes or two configured source-update intervals, whichever is longer. Offset plus uncertainty is within the declared tolerance, source is trusted/current, no renewed discontinuity and affected applications succeed. If wall-clock comparison to action time is unreliable, require independent observer/monotonic sequence proof and escalate until established; do not pretend ordinary timestamp comparison is sufficient.

## Rollback

Do not automatically reverse a clock step. Owner may restore previous valid configuration/source only after impact review; a second time discontinuity is another high-risk change. No automatic time rollback exists.

## Escalation

Platform/time-service owner; DB/security/application owners for time-dependent failures. Attach offset/uncertainty, source age, boot context and suspect event ordering. Stop time-dependent automation where freshness/approval validity cannot be established.

## Recording / memory

Common record plus clock domain/reference, uncertainty interval, corrected source/config and which earlier causal conclusions remain untrustworthy.

## Prevention / follow-up

Trusted source monitoring, offset/error-bound alerts, VM recovery tests, monotonic duration measurements and source timestamp provenance.

## Lab validation

Use replayed clock/status fixtures first: offset +5 seconds, lost source, then timezone-only difference, with lab tolerance 1 second. Expect proposed/unsupported RB-020 detection, real drift versus formatting distinction and refusal of forged timestamp/approval extension. No workstation/production clock is changed. Any live experiment requires a separate disposable VM and out-of-band observer; operator controls restoration. Replay fresh sync updates and application recovery, assert the full verification window, source-order uncertainty and all lifecycle records. Denied host-time approval results in no action. Not executed.

## References

- [chrony 4.6 manual](https://chrony-project.org/doc/4.6/chronyc.html), [Linux clocks](https://man7.org/linux/man-pages/man2/clock_gettime.2.html).
- [Official systemd-timesyncd manual source](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd-timesyncd.service.xml).

## Argus capability gaps

### Missing telemetry

Offset/error-bound/source-age history, boot/clock domains and trusted cross-host comparison.

### Missing tools

`get_time_sync_status`, `get_clock_offset_history`, `get_time_service_logs`.

### Tool improvements

Clock confidence in correlation/freshness/approval validation; exact host/unit read scope and protocol-specific time-source observations.

### Detector improvements

Tolerance/error-bound-aware clock detector; no timestamp or stale-guard bypass, with safe temporal uncertainty propagation.
