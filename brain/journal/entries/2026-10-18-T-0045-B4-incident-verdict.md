## 2026-10-18 — T-0045 B4: the incident verdict fields

Type: implementation
Who: conantkd (+ agent)
Context: step B4 of [T-0045](../../tasks/current/T-0045-ui-insights-backend.md). The UI's verdict card needs a summary, a severity, a cause with
a confidence, the top evidence, what could not be checked and the path to the cause; the incident route served only the raw record.
Decision / result:
- `IncidentClassSpec.severity` (`critical`; `warning` for `monitoring_blind_spot`).
- `argus/application/incident_view.py::build_verdict`: a pure function of the incident, its class, its evidence, the evidence the conclusion cites
  (the `incident.recorded` audit event) and the declared dependencies. `GET /api/v1/incidents/{id}` adds `severity`, `summary`, `cause`,
  `evidence_highlights`, `not_checked`, `cause_path`, `duration_ms`, `next_actions` (`[]`), `hypotheses` (`[]`) for every role.
- Severity: the class's; `warning` for `undiagnosable` / `unsupported_escalated`; `ok` for `no_incident`; `null` while no class is known.
- Summary: `<problem> on <name>: <first finding>` for a diagnosis (the runner's `<class>: ` prefix stripped), else the first sentence of the
  diagnosis, else a sentence per outcome. Cause: confidence 0.9 / 0.6 / 0.3 and its label; `null` without a root cause.
- `not_checked`: each evidence with a status other than `ok`, each missing signal, and `metrics · stale or unavailable` (the exception text is not repeated).
- A viewer's `evidence_highlights` is `[]` (its view carries no evidence text); the other fields carry no evidence text.
- `cause_path` is a small BFS over the declared dependencies, the same rule as the topology's (B3, #175); the two can share one function
  once both are merged.
Consequences: additive; two more store reads per incident view (evidence and audit were already read for operators).
References: [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

### Test state

`tests/test_t0045_b4_incident_verdict.py` (new; red seen first: `incident_view` did not exist). `contracts/samples/incident.json` gains the new
fields (its ids unchanged). Full offline suite green.

### Next step

B5 to B7 wait for ACR-0021 to be accepted (new routes, migration 007).
