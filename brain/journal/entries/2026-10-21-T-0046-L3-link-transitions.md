## 2026-10-21 — T-0046 L3: the scheduler records link-state changes (off until deployed)

Type: implementation
Who: juanbetancurm (+ agent)
Context: ACR-0025 §3.1. L2 (#220) added `link_event`; nothing wrote it. ARCHITECTURE §7.3 already describes this step
(1.8.24), so no architecture change.
Decision / result:
- `application/link_transitions.py` (`LinkTransitions`): for every container owner with a declared container
  dependency on its own host, read `dependency_probes(owner)` and derive each link's state with `application/links.py`
  and the owner's `link_warning_ms`. A row and an audit event `link.changed` (actor `scheduler`, the previous and the
  new state) only when the state changes, and once when the process starts. A broken link's reason is the map's.
- A host whose Prometheus cannot be read (`MetricsUnavailable`) is skipped for the tick: no `unknown` burst and no
  recovery burst. A stale read is `unknown`. A host-kind dependency is never probed or recorded.
- `reconcile_firing_alerts.link_states.enabled` in `deploy/scheduler/schedules.yaml`, shipped `false`; refused when the
  reconcile itself is off (it runs on that tick). The scheduler runs it after the alert reconciliation; its failure is
  logged and never stops the alerts.
- Not recorded: the topology's fallback for an owner whose exporter has no per-dependency samples (it shows the
  owner's `dependency_probe_min`); without a per-dependency sample the recorder writes `unknown`.
Consequences: no deploy change while it stays off; L5 turns it on on vm-095 (migration 009 is already applied there).
Next: L4, the map, the charts and the investigation read the table.
References: [ACR-0025](../../architecture/changes/ACR-0025-live-dependency-graph.md),
[T-0046](../../tasks/current/T-0046-live-dependency-graph.md), #220.
