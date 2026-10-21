## 2026-10-21 — T-0046 L4: the map, the incident charts and the investigation read the recorded link changes

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0025 §3.3 to §3.5. L3 (#226) records each declared container link's state changes in `link_event`;
nothing read them. ARCHITECTURE (1.8.24) already describes this step, so no architecture change.
Decision / result:
- The map: each dependency edge adds `required` and `since` (its last recorded transition, only when that state is
  the state now; else `null`). A broken required link is a critical `dependency_broken` problem of its owner, except
  when the owner is idle. The overlay of an incident re-judges a box with the same rule. New store read
  `latest_link_events()` (Postgres `DISTINCT ON`, SQLite `MAX(id)`).
- The incident charts: `link_broken`, `link_slow` and `link_recovered` events in the window, for the links of the
  target and of its declared dependencies (same host). `link_recovered` is an `ok` after `broken` or `slow`, judged
  with the state before the window (24 h back); an `ok` after nothing or `unknown`, and `unknown` itself, are no event.
- `network.link_states` (`read_link_states`): Level 2, `READ_ONLY_SAFE`, in-worker (`argus_internal`), tag
  `link_states`, which no class has; `max_per_incident: 2` in `config/policy.yaml`. Per link: the state now (the
  recorder's own rule, `link_transitions.read_links`, on the latest probe), else the last recorded state, `since`,
  and the transitions of the last `minutes` (≤ 240). An unreadable Prometheus gives a partial answer.
- The recorder's per-link logic moved into `read_links`, shared by the recorder and the read.
- `contracts/samples/topology*.json` and `docs/API-FOR-UI.md` show the new fields.
Consequences: the map shows a new critical problem when a required link breaks, and the overview counts that owner
as failed. Offering the read to classes is L6, after an evaluation batch. Next: L5, deploy and measure on vm-095.
References: [ACR-0025](../../architecture/changes/ACR-0025-live-dependency-graph.md),
[T-0046](../../tasks/current/T-0046-live-dependency-graph.md), #226.
