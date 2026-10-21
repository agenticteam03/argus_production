# T-0046 — A live dependency graph: link states over time, in the map, the charts and the investigation

| Field | Value |
|---|---|
| Status | `in progress` — [ACR-0025](../../architecture/changes/ACR-0025-live-dependency-graph.md) accepted (#214); L1 merged (#219), L2 merged (#220), L3 in review (#226), L4 in review (`task/T-0046-l4-read-link-history`, on top of L3) |
| Phase | next phase, area B (separate track of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md)) |
| Architecture | ACR-0025 (`accepted`, applied in 1.8.24 by L1) |
| Branch | one branch per step: `task/T-0046-l<n>-<slug>` |
| Owner | `juanbetancurm` (+ agent); review `conantkd` |
| Needs the VM lease | L5 only (deploy on vm-095) |

## Goal (plain language)

The map already shows whether each connection works *right now*. This task makes Argus **remember** when a connection
broke and came back, show it on the incident charts ("link to the cache broke 40 s before the API's errors"), and let
the investigation read it as evidence. No new traffic to the monitored hosts: it reuses the probe the exporter already
runs on every scrape.

## Steps (each a PR, red tests first)

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

### L5 — Deploy and measure (vm-095 lease)
- `db-migrate.sh` (the new migration), the new image, `link_states.enabled: true`; `nonint-check` before and after.
- Run SC-03 and SC-07 once each: the transitions are recorded with the right order against the errors.

### L6 — Offer `network.link_states` to its classes
- Add the `link_states` tag to `dependency_unavailable`, `health_check_failed`, `nginx_upstream_failure`
  (`argus/detectors/classes.py`: a teammate reviews it, OP-014 step 8; never a self-merge); at least five evaluation
  cases that need it
  (SC-03, SC-07, SC-08 variants); a full evaluation run before and after; accuracy not lower, hard checks at 0.

## Out of scope

Undeclared connections, cross-host links, a push channel to the browser (ACR-0025 §3.7).
