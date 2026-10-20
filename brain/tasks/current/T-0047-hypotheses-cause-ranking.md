# T-0047 — Explicit hypotheses and a transparent cause ranking

| Field | Value |
|---|---|
| Status | `proposed` — steps H1–H6 wait for [ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md) to be accepted (with its second approval) |
| Phase | next phase, area C (separate track of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md)) |
| Architecture | ACR-0024 (`proposed`) |
| Branch | one branch per step: `task/T-0047-h<n>-<slug>` |
| Owner | `juanbetancurm` (+ agent); review `conantkd` (owner of the built reads, T-0034 to T-0040) |
| Needs the VM lease | the evaluation runs on the VMs and H6 (deploy on vm-095) |

## Goal (plain language)

Today Argus gives one answer and says how sure it feels. After this task it lists the causes it considered, which
evidence supports or contradicts each one, which ones it ruled out, and a score computed from the evidence (never by the
model, never a percentage). The operator sees why the chosen cause beats the others, and the evaluation can check that
the wrong causes were ruled out.

## Steps (each a PR, red tests first)

### Before H1 — what is already measured (EVAL-offers, 2026-10-19)
The five built reads (`metrics.cpu_history`, `metrics.compare_baseline`, `knowledge.prior_incidents`,
`analysis.trace_request_path`, `analysis.diagnostic_snapshot`) are offered to no class. EVAL-offers measured offering
them one by one (61 cases × 5 trials): they are used and change little, so offering them alone is not the next step.
H4 measures them again with hypotheses in the decisions.

### H1 — The schema and the harness checks, log-only
- `Hypothesis`; the optional fields on `Conclude`, `Escalate`, `UseReadTools` (ACR-0024 §3.1); decision tool schemas.
- The §3.2 checks, first **logging** a would-be refusal (`hypothesis.invalid` audit) instead of refusing.
- The system prompt explains how to state hypotheses.
- `ARCHITECTURE.md` applied with this first code (ACR-0024 §6): §5.5, §7.1, §10.6, §11.3, §12.2, §16.1, §21.2, the
  version and the changelog, describing the whole accepted change; later steps only tick what they build.
- **Tests:** each check on fixtures (fabricated id, root cause without a target observation, ruled out without against,
  chosen not supported, more than five, `target: null` that is not external, an external hypothesis chosen); old
  replies without hypotheses still convert.

### H2 — Storage, ranking and the working-memory slot
- Migration `<next free number>_incident_hypothesis.sql` (insert-only) and both stores; `db-check` checks.
- `application/ranking.py` + `config/ranking.yaml` (added to `SELF_MERGE_PROTECTED`); `ranking_disagrees`.
- `context.py`: the "Hypotheses under test" slot (≤ 300 tokens, never dropped once present).
- **Tests:** deterministic ranking; ties (records no other hypothesis cites); weights from config; generic kinds
  counted once (two hypotheses, one citing every alert, ranked by the target observation); insert-only; the slot's
  bound and order.

### H3 — The incident answer
- `incident_view.py`: `hypotheses` and `ranking_disagrees` (ACR-0024 §3.6); viewer gets counts, not ids.
- Contract, sample, `docs/API-FOR-UI.md`.

### H4 — Evaluation
- `expected_hypotheses` labels on the existing cases (SC-01 to SC-09); top-1 / top-3 accuracy over the ranking;
  ruled-out recall; hard check `unsupported_root_cause` = 0.
- A run with the H1 checks still log-only; then the harness **enforces** them only if accuracy is not lower.
- The built reads measured again with hypotheses, one batch per read (as EVAL-offers); a read is offered to a class
  only when its batch improves that class. Offering changes the class registry (`argus/detectors/classes.py` tags),
  so that PR needs a teammate's review (OP-014 step 8), never a self-merge.

### H5 — `analysis.anomaly_summary`
- Onset, deviation from the B7 baseline, which onset came first (ACR-0024 §3.7); offered to no class; then offered to
  `dependency_unavailable` and `container_restart_loop` with an evaluation batch (a class-registry change: a teammate
  reviews it).

### H6 — Deploy (vm-095 lease)
- `db-migrate.sh` (the new migration), the new image; `nonint-check`; SC-03 and SC-07 once each: the hypotheses, the ruled-out cause
  and the ranking visible in the UI.

## Out of scope

Case similarity and a prior from confirmed incidents (T-0048 first); external knowledge (ACR-0022); actions (ACR-0019).
