# T-0046 — A live dependency graph: link states over time, in the map, the charts and the investigation

| Field | Value |
|---|---|
| Status | `in progress` - L1-L6 merged and deployed (L6: #322, DEPLOY-16028c7); SC-03 and SC-07 checked live on 2026-10-26 ([evidence](../../execution/history/T-0046-l6/step-03/evidence.md)); **left:** the model arm (`health_check_failed`) once the replay's `now` is pinned |
| Phase | next phase, area B (separate track of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md)) |
| Architecture | ACR-0025 (`accepted`, applied in 1.8.24 by L1); [ACR-0031](../../architecture/changes/ACR-0031-replay-link-probe-history.md) accepted and applied in 1.8.36 in this PR |
| Branch | `task/T-0046-l6-sample-history` (one PR across the remaining L5 temporal correction and L6, per developer direction) |
| Task owner | `juanbetancurm`; implementation branch author `conantkd` (+ agent); review required from `juanbetancurm` |
| Needs the VM lease | L5 deployment and SC-03/SC-07 verification (both leases; the agent on vm-095 changes) |

## Goal (plain language)

The map already shows whether each connection works *right now*. This task makes Argus **remember** when a connection
broke and came back, show it on the incident charts ("link to the cache broke 40 s before the API's errors"), and let
the investigation read it as evidence. No new traffic to the monitored hosts: it reuses the probe the exporter already
runs on every scrape. The recorder reads the retained sample history by source timestamp and resumes from a per-link
cursor after restarts or temporary Prometheus outages. The cursor lives in Argus Postgres on vm-095; vm-166 remains the
Prometheus sample source.

## Steps (completed phases remain historical; the remaining L5 correction and L6 ship in one PR)

### L1 — The link-state rules in one place, and the inventory mapping
- `application/links.py`: the state of one link from a probe sample (`ok` / `slow` / `broken` / `unknown`), moved out of
  `topology.py` unchanged (the topology tests stay green).
- `config_adapters.py`: `depends_on` accepts `{ref, port, required}`; a plain ref keeps today's meaning. Refused: a port
  the dependency does not list, a `port` on a host-kind ref, a dependency on another host.
- `ARCHITECTURE.md` applied with this first code (ACR-0025 §6): §5.8, §7.1, §7.3, §12.2, §16.1, the version and the
  changelog, describing the whole accepted change; later steps only tick what they build.
- **Tests:** the existing topology tests; the loader refusals (a port the dependency does not list, a `port` on a host
  ref, another host); a mapping and a plain ref give the same edge.

### L2 — `link_event` (migration 009) and the store
- Migration `009_link_event.sql`, insert-only (SELECT, INSERT); SQLite table and triggers; `add_link_event`,
  `link_events(owner_or_dependency, start, end)`; three `db-check` checks (insert ok, UPDATE and DELETE refused).
- **Tests:** insert-only on both stores; the read window; `tests/test_postgres.py`.

### L3 — The scheduler records transitions
- The scheduler gets the `MetricsPort` (a new read for it). On each reconcile tick, per owner with a declared
  container dependency: `dependency_probes` on the owner's own host; a row only
  when the state changes (and once at startup); audited `link.changed`; `link_states.enabled` in
  `deploy/scheduler/schedules.yaml` (default off).
- **Tests:** no row while nothing changes; one row per change; a stale or missing sample → `unknown`; a host's read never
  goes to another host's Prometheus; a Prometheus failure skips the tick for that host only (no `unknown` burst); a
  host dependency is never probed.

### L4 — The map, the charts and the investigation read it
- Topology: `since`, `required`; a broken required link is a critical `dependency_broken` problem on its owner.
- Incident metrics: `link_broken` / `link_recovered` / `link_slow` events in the window.
- `network.link_states` (Level 2, `argus_internal`, tag `link_states`, which no class has, `max_per_incident` 2):
  registered but **offered to no class** (a Level 1 read would reach every class at once).
- Contract and samples; `docs/API-FOR-UI.md`.
- **Tests:** the fields and events; the read's result as a stored observation; viewer/operator answers unchanged
  otherwise.
- **Follow-up (#227 review):** the recorder writes every link once at startup, so each deploy repeated the states it
  had recorded; the stores' reads (`link_events`, `latest_link_events`) now skip a row that repeats its link's
  previous state, ordered by time then id on both stores. `since` and the chart events survive a restart.

### L5 — Deploy and measure (vm-095 lease)
- `db-migrate.sh` (the new migration), the new image, `link_states.enabled: true`; `nonint-check` before and after.
- Run SC-03 and SC-07 once each: the transitions are recorded with the right order against the errors.
- **Temporal correction in the remaining L5 work:** `MetricsPort` reads bounded four-hour range history at source
  scrape timestamps; migration 014 persists each link's source-sample cursor; an event, chained audit row and cursor
  update commit atomically. On a Prometheus outage the cursor does not move; once it returns, retained samples replay.
  If the cursor is older than the four-hour window, the gap is made explicit with `unknown` before replaying newer
  samples. Migration and application deployment are on vm-095; vm-166's Prometheus remains unchanged.
- **Validation:** test a transition sequence within one scheduler interval, interruption/restart, Prometheus down/up,
  an over-window cursor, PostgreSQL permissions and `argus db check`; run the full evaluation before and after.

### L6 — Offer `network.link_states` to its classes
- Add the `link_states` tag to `dependency_unavailable`, `health_check_failed`, `nginx_upstream_failure`
  (`argus/detectors/classes.py`: a teammate reviews it, OP-014 step 8; never a self-merge); at least five evaluation
  cases that need it
  (SC-03, SC-07, health-check dependency failure, and SC-08 broken/slow upstream); deterministic baselines read and
  consume the evidence. Full evaluation before and after; accuracy not lower, hard checks at 0.
- **As measured (2026-10-25):** baseline only. Each of the five cases fails without the offer (`test_t0046_l6_eval.py`):
  SC-03, SC-07 and the health case on the root cause, the SC-08 cases on the mechanism. Control 57/66, treatment 62/66.
  The `model_loop` arm for `health_check_failed` needs the replay's `now` pinned and is not measured.

## Current handoff

- Red observed before the history implementation: three regression checks failed for dropped intermediate transitions,
  restart replay and the missing durable cursor table.
- The focused suite includes the Prometheus source-timestamp adapter, four-hour bound, store invariants, both staleness
  boundaries, a silent exporter and the five baseline replay cases with their control arm. The paired 66-case baseline
  evaluation (control 57, treatment 62) is stored in `execution/history/T-0046-l6/step-02/`; hard checks remained zero.
  Four unrelated existing failures appear in both arms.
- Full offline pytest completed; all 15 failures are Bash-backed tests blocked by the WSL launcher (`/bin/bash` missing).
  PostgreSQL runtime test passes in GitHub CI; locally it is unavailable because Docker is not running.
- Read-only pre-deployment probes ran on both VMs: vm-095 is at `c8d8594`, vm-166 at `bdcd048`; both report
  `LAB BASELINE OK` and `NO INTERFERENCE`. No application deploy or migration ran because PR #322 is unmerged. The
  sanitized evidence and commands are archived under `execution/history/T-0046-l6/step-01/`.
- PR #322 is open; its first CI run found a UTC JSON timestamp formatting mismatch in the Postgres test, corrected in
  `26aeb79` (`+00:00` normalizes to `Z`). Latest test and frontend jobs pass; wait for `juanbetancurm` review. The author
  must not self-approve or merge.

## Out of scope

Undeclared connections, cross-host links, a push channel to the browser (ACR-0025 §3.7).
