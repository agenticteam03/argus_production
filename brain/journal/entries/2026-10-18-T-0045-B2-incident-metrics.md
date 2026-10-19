## 2026-10-18 — T-0045 B2: incident metrics with kind, thresholds, events, the incident band and a summary

Type: implementation
Who: conantkd (+ agent)
Context: step B2 of [T-0045](../../tasks/current/T-0045-ui-insights-backend.md); builds on B1 (thresholds, #173).
Decision / result:
- `config/ui-incident-signals.yaml`: every entry has a `kind` (`memory`, `restarts`, `cpu`, `latency`, `health`, `disk`,
  `database`, `network`, `other`), validated (default `other`).
- `GET /api/v1/incidents/{id}/metrics`: per series `kind`, `thresholds` (B1's lines scaled like the values) and
  `detector_threshold` (the scaled critical line, on the `fired` series only); at the top `incident_from`, `incident_to`
  (`null` while open), `events` and a template `summary`.
- Events: `restart` where `container_restart_count` rises and `oom_kill` where `oom_killed` goes 0 to 1 (container targets
  only; read even when the class chart does not draw them; a failed read leaves no event, not a broken answer);
  `alert_fired` / `alert_resolved` from the incident's `alert_occurrence` rows that fall inside the window. `deploy` waits
  for B6. A first sample already at 1 is not a new OOM.
- Summary: one template per class and per fired state (`SUMMARIES`), filled with the extreme of the judged series;
  an unreadable series says the state is unknown, never healthy. No address, URL or model text.
Consequences: additive; the UI ignores the new fields until it reads them. Up to two extra range reads per container
incident, inside the existing 30 s / 10 min shared cache.
References: [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

### Test state

`tests/test_t0045_b2_incident_metrics.py` (new; red seen first: `KINDS` did not exist); `test_acr0017_incident_metrics.py`
(the series key set gains three fields); `contracts/samples/incident-metrics.json` regenerated. Full offline suite green.

### Next step

B3 (topology: health, problems, per-dependency links) and B4 (the incident verdict fields).
