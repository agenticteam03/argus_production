## 2026-10-21 — T-0047 H3: the hypotheses in the incident answer

Type: implementation
Who: juanbetancurm (+ agent)
Context: H2 (#236) stores each decision's hypotheses with their score and rank. H3 is ACR-0024 §3.6: show them in
`GET /api/v1/incidents/{id}`, the slot the UI already had (`"hypotheses": []`). ARCHITECTURE §7.1 already describes
this answer, so the version stays 1.8.28.
Decision / result:
- `incident_view.hypotheses_view`: the final decision's rows, by rank: `{id, statement, cause_class, target, relation,
  status, rank, chosen, support: {score, for, against}}`, plus `ranking_disagrees` (the chosen one is not ranked
  first). Derived from the stored rows; no model call.
- `for` / `against` count the cited records that are stored evidence of the incident, each once (an id cited twice,
  or not stored, is not counted). Operators and approvers also get `support_ids` / `against_ids`; a viewer gets the
  counts only, as for `evidence_highlights`.
- The UI contract's scripted run now concludes with two hypotheses; `contracts/samples/incident.json` gained them by
  hand (the other samples are unchanged). `docs/API-FOR-UI.md` describes the fields.
Consequences: the frontend can show the list and the "the evidence favours <first>" note. H4 measures the ranking.
References: [ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), #236.
