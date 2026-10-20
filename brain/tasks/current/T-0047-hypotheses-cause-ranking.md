# T-0047 — Explicit hypotheses and a transparent cause ranking

| Field | Value |
|---|---|
| Status | `proposed` — step 0 needs no ACR; steps H1–H6 wait for [ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md) to be accepted (with its second approval) |
| Phase | next phase, area C (separate track of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md)) |
| Architecture | ACR-0024 (`proposed`) |
| Branch | one branch per step: `task/T-0047-h<n>-<slug>` |
| Owner | `juanbetancurm` (+ agent); step 0 with `conantkd` (owner of T-0036 to T-0040); review `conantkd` |
| Needs the VM lease | the evaluation runs on the VMs and H6 (deploy on vm-095) |

## Goal (plain language)

Today Argus gives one answer and says how sure it feels. After this task it lists the causes it considered, which
evidence supports or contradicts each one, which ones it ruled out, and a score computed from the evidence (never by the
model, never a percentage). The operator sees why the chosen cause beats the others, and the evaluation can check that
the wrong causes were ruled out.

## Steps (each a PR, red tests first)

### Step 0 — Turn on the reads that are already built (no ACR)
Offer them class by class, one class family per PR, each with at least five evaluation cases that need the read and a
full evaluation run before and after (accuracy not lower, hard checks at 0):
- `container_restart_loop`: `metrics.compare_baseline` (memory);
- `cpu_saturation`: `metrics.cpu_history` and `metrics.compare_baseline` (cpu);
- `disk_pressure`: `metrics.compare_baseline` (disk);
- `dependency_unavailable`, `health_check_failed`: `analysis.trace_request_path`;
- the classes where one call replaces several reads: `analysis.diagnostic_snapshot`;
- every enabled class: `knowledge.prior_incidents` (until T-0048, as context only).
The tags each read needs are checked against `argus/capabilities/catalog.py` and `argus/detectors/classes.py` at the
start of the step.

### H1 — The schema and the harness checks, log-only
- `Hypothesis`; the optional fields on `Conclude`, `Escalate`, `UseReadTools` (ACR-0024 §3.1); decision tool schemas.
- The §3.2 checks, first **logging** a would-be refusal (`hypothesis.invalid` audit) instead of refusing.
- The system prompt explains how to state hypotheses.
- **Tests:** each check on fixtures (fabricated id, root cause without a target observation, ruled out without against,
  chosen not supported, more than five); old replies without hypotheses still convert.

### H2 — Storage, ranking and the working-memory slot
- Migration `009_incident_hypothesis.sql` (insert-only) and both stores; `db-check` checks.
- `application/ranking.py` + `config/ranking.yaml` (added to `SELF_MERGE_PROTECTED`); `ranking_disagrees`.
- `context.py`: the "Hypotheses under test" slot (≤ 300 tokens, never dropped once present).
- **Tests:** deterministic ranking; ties; weights from config; insert-only; the slot's bound and order.

### H3 — The incident answer
- `incident_view.py`: `hypotheses` and `ranking_disagrees` (ACR-0024 §3.6); viewer gets counts, not ids.
- Contract, sample, `docs/API-FOR-UI.md`; ARCHITECTURE applied (ACR-0024 §6).

### H4 — Evaluation
- `expected_hypotheses` labels on the existing cases (SC-01 to SC-09); top-1 / top-3 accuracy over the ranking;
  ruled-out recall; hard check `unsupported_root_cause` = 0.
- A run with the H1 checks still log-only; then the harness **enforces** them only if accuracy is not lower.

### H5 — `analysis.anomaly_summary`
- Onset, deviation from the B7 baseline, which onset came first (ACR-0024 §3.7); offered to no class; then offered to
  `dependency_unavailable` and `container_restart_loop` with an evaluation batch.

### H6 — Deploy (vm-095 lease)
- `db-migrate.sh` (009), the new image; `nonint-check`; SC-03 and SC-07 once each: the hypotheses, the ruled-out cause
  and the ranking visible in the UI.

## Out of scope

Case similarity and a prior from confirmed incidents (T-0048 first); external knowledge (ACR-0022); actions (ACR-0019).
