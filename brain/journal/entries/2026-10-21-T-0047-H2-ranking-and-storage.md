## 2026-10-21 — T-0047 H2: the hypotheses ranked, stored and carried to the next step (ARCHITECTURE 1.8.28)

Type: implementation
Who: juanbetancurm (+ agent)
Context: H1 (#228) gave the decisions their hypotheses and the harness its log-only checks. H2 is ACR-0024 §3.3-§3.5:
the score and the ranking, the `incident_hypothesis` table and the "Hypotheses under test" slot of the context.
Decision / result:
- `application/ranking.py`: the score by what each cited record is evidence of (own target per record up to
  `max_target_records`; the generic kinds once per kind and side; an unknown id counts for nothing); ties by records
  no other hypothesis cites, then the order given; `ranking_disagrees`. Weights in `config/ranking.yaml` (validated
  at startup, fail closed; the defaults when the file is missing).
- Migration 012 `incident_hypothesis` (insert-only for the runtime role; the db-check proves it) and the same table
  with insert-only triggers in SQLite; `add_hypotheses` and `hypotheses` on both stores.
- Both runners rank and store each decision's hypotheses after its audit; a step already stored is skipped (a run
  resumed after a crash), and a failure to store never stops the run.
- Found while building: §3.1's optional list on `UseReadTools` had no way to arrive, so a read step now states its list
  in one `state_hypotheses` call beside its read calls (not a read; refused alone, twice or beside a decision). The
  context shows the latest list (≤ 1200 characters, about 300 tokens). ARCHITECTURE 1.8.28 says so (§5.5, §11.3).
- The T-0047 H4 step now says to leave out problems on evidence references without `target` / `kind` (#228 review).
Consequences: nothing is shown yet: H3 adds the hypotheses and `ranking_disagrees` to the incident answer. Migration
012 must run before the image that writes the table (`db-migrate.sh`); until then a store without the table logs the
failure and the run goes on.
References: [ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md),
[T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md), #228.
