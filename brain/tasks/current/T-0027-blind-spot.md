# T-0027 — The monitoring blind spot class (`monitoring_blind_spot`, RB-014)

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (code, tests, evaluation cases) done; step 2 (VMs) next |
| Phase | 7 — monitoring and detection ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): detectors restart loop, health, dependency, **blind spot**) |
| Architecture | no change (no ACR): §3 class table (`monitoring_blind_spot` · RB-014 · `evidence_pack`), §9 (unknown is never healthy, G-007) |
| Branch | `task/T-0027-blind-spot`, on top of `task/T-0026-alert-resolution` (the VMs run it) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | step 2: the agent image and both hosts' Prometheus rules; a scrape target stopped on vm-166 |

## Goal (plain language)

When one of the exporters that feed a host's Prometheus stops (node-exporter, cAdvisor, the db-probe), the signals it
feeds come back empty. Before this task a health check of that host could then end `no_incident` ("healthy"), which
is exactly the mistake Argus must never make: missing data is unknown, not healthy. Now the host's Prometheus is
asked how many of its scrape targets are down; one or more is a **monitoring blind spot** incident, escalated with the
fixed evidence pack and no model call, and the alert `ArgusScrapeTargetDown` brings it in.

## Decisions (2026-10-09, `conantkd` + agent)

- Signal `scrape_targets_down = count(up{argus_host="$host"} == 0) or vector(0)`: general (every scrape job of the
  host, whatever it feeds), no inventory change. An expected target that is absent from the config (H3/H8 in RB-014)
  is not covered: that needs a pinned list of expected jobs, a follow-up.
- The class is registered for **host** targets, **before** `disk_pressure`: unknown comes before any verdict.
  Strategy `evidence_pack` (§3): no model, no diagnosis claimed.
- Alert `ArgusScrapeTargetDown`: `up{job=~"argus-v18-.*"} == 0` for 2 minutes (RB-014: two scrape intervals and more).
- The gate exporter (`argus-v18-exporter`) down keeps ending `undiagnosable` with the RB-014 reference (unchanged).
- §21.2: 5 labeled cases (abstain, 0 model calls). The test that every enabled class has its cases now reads the
  registry; `disk_pressure` (registered by T-0024 without cases) is listed in `AWAITING_CASES` for the quality lane.

## Steps

1. **Code and tests** (done 2026-10-09): `tests/test_t0027_blind_spot.py` (10; red seen: the class did not exist and a
   check of a host with node-exporter down ended `no_incident`), 5 cases in `tests/eval/cases/blind-*.yaml`,
   `test_every_registered_class_has_its_cases_or_is_listed_as_awaiting_them` (red seen without the cases).
2. **VMs:** agent image on vm-095; both hosts' Prometheus reloaded with the new rule; on vm-166 stop
   `argus-v18-node-exporter`: `ArgusScrapeTargetDown` fires, the pulled alert opens a `monitoring_blind_spot`
   incident on `vm-166/host:vm-166`, escalated with the evidence pack, no model call; start it again: the alert
   resolves (T-0026); NO INTERFERENCE.

## Done when

The step 2 incident is escalated as `monitoring_blind_spot` from the pulled alert, its occurrence is resolved after
the exporter is back, and both VMs show NO INTERFERENCE.
