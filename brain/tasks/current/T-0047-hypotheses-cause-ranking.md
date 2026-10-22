# T-0047 — Explicit hypotheses and a transparent cause ranking

| Field | Value |
|---|---|
| Status | `in progress` — [ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md) accepted (#215); H1 merged (#228); H2 merged (#236); H3 merged (#237); both deployed on vm-095 (#239); H4 step 1 (the metrics) merged (#245); H5 step 1 (`analysis.anomaly_summary`, offered to no class) merged (#252); H5 step 2 part A (per-target range fixtures in the replay) merged (#267); part B (the read offered to two classes) in review (`task/T-0047-h5s2b-anomaly-offer`), its model batch not run yet |
| Phase | next phase, area C (separate track of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md)) |
| Architecture | ACR-0024 (`accepted`, applied in 1.8.27 by H1) |
| Branch | one branch per step: `task/T-0047-h<n>-<slug>` |
| Owner | `juanbetancurm` (+ agent); review `conantkd` (owner of the built reads, T-0034 to T-0040) |
| Needs the VM lease | the evaluation runs on the VMs and H6 (deploy on vm-095) |

## Goal (plain language)

Today Argus gives one answer and says how sure it feels. After this task it lists the causes it considered, which
evidence supports or contradicts each one, which ones it ruled out, and a score computed from the evidence (never by the
model, never a percentage). The operator sees why the chosen cause beats the others, and the evaluation can check that
the wrong causes were ruled out.

## Steps (each a PR, red tests first)

### Before H1 — what is already measured
The five built reads (`metrics.cpu_history`, `metrics.compare_baseline`, `knowledge.prior_incidents`,
`analysis.trace_request_path`, `analysis.diagnostic_snapshot`) are offered to no class. What is measured so far:
- **EVAL-offers** (2026-10-19, 61 cases × 5 trials, one batch per offer): `cpu_history` and `disk_history` are used
  and change nothing; `request_path` 0.72 → 0.74; `search_logs` called in 4 of 50 health runs; `baseline`
  (`compare_baseline`) in 1 of 25 cpu runs.
- **EVAL-snapshot** (#121, 2026-10-13): `diagnostic_snapshot` offered to `health_check_failed` lowered it
  (0.88 → 0.72), so it was not offered.
- **`prior_incidents`: not measured.** The replay store is empty, so any precedent would be invented.

So offering them alone is not the next step. H4 measures them again with hypotheses in the decisions. Separately,
`conantkd` measures `compare_baseline` for `container_restart_loop` once B7's baseline is deployed (#202).

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
  - Step 1 (built): the label, the replay's final list, the metrics and the hard check. 15 cases are labeled, the
    ones whose cause is not the target (`dep-*`, `nginx-slow-*`, `pg-leaker-*`): the cause supported, the target (the
    victim) ruled out; the others fall back to `root_cause`. Replays are fresh, so the #228 note (references without
    `target` / `kind`) applies only to recorded investigations.
- A run with the H1 checks still log-only; then the harness **enforces** them only if accuracy is not lower.
- Leave out of the problem rate the problems on evidence references without `target` / `kind`: an investigation
  checkpointed before H1 holds such references (`conantkd`, #228 review).
- The built reads measured again with hypotheses, one batch per read (as EVAL-offers): `cpu_history`,
  `disk_history`, `compare_baseline`, `trace_request_path`, `search_logs` and `diagnostic_snapshot`;
  `prior_incidents` only once the replay store holds recorded incidents to recall. A read is offered to a class only
  when its batch improves that class. Offering changes the class registry (`argus/detectors/classes.py` tags),
  so that PR needs a teammate's review (OP-014 step 8), never a self-merge.

### H5 — `analysis.anomaly_summary`
- Onset, deviation from the B7 baseline, which onset came first (ACR-0024 §3.7); offered to no class; then offered to
  `dependency_unavailable` and `container_restart_loop` with an evaluation batch (a class-registry change: a teammate
  reviews it).
  - Step 1 (built): the read, offered to no class. The model names the incident class (the 8 registered names); the
    prometheus executor holds the warning lines and the per-class signal lists from startup. A 0/1 state signal
    (`dependency_probe_min`, `db_up`, `health_unhealthy`, `oom_killed`, `scrape_targets_down`) has no line in
    `signals.yaml`: its bad state is its line. A "below" signal is compared with the baseline's p5, the others with its
    p95. Left for step 2: the eval fixtures read one series per signal whatever the target, so a dependency case needs
    per-target `range` fixtures before the batch can tell which onset came first.
  - Step 2, part A (built): `range_by_target.<target>.<signal>` in the replay's prometheus fixtures gives a target
    other than the case's its own series (a target named there never falls back to `range`, which stays the case
    target's). The six dependency cases (`dep-*`, `ambiguous-dep-all-running`) got the victim's `dependency_probe_min`
    and the dependency's own memory and restart series; labels unchanged. The offline evaluation of
    `tests/eval/cases` is identical before and after (registered: 32/61; `--strategy baseline`: 57/61; hard 0).
    The six `restart-*` cases got `restarts_10m` and `oom_killed` series in `range`, derived from their own restart
    history and scaled so the last sample is the snapshot's value (three cases' restart-count history undercounts
    it: `restart-crash-01`, `restart-crash-02`, `restart-oom-01`). `range_earlier` (the baseline window) stays one
    series per signal, not per target: a dependency's 24 h baseline in the replay is the case target's.
  - Step 2, part B (built, batch pending): the `anomaly` tag on `dependency_unavailable` and `container_restart_loop`
    (a class-registry change: `conantkd` reviews). The offline evaluation of `tests/eval/cases` is unchanged
    (registered 32/61, `--strategy baseline` 57/61, hard 0): the baseline asks no model, so a tool offer changes nothing
    without one. The model batch decides whether the offer stays: the 12 cases of the two classes (`dep-*`,
    `ambiguous-dep-all-running`, `restart-*`) in their own folder on vm-095, `--strategy model_loop` (the registered
    strategy of `container_restart_loop`; `dependency_unavailable` runs `baseline`, D-003, which asks no model),
    5 trials, before (an image of main, the read registered but offered to no class) and after (an image of this
    branch); accuracy not lower per class and hard 0, else the tag is removed. The deployed `6c83da3` predates H5, so
    both runs need images built for the evaluation (`ARGUS_EVAL_IMAGE`), or the next deploy for "before".

### H6 — Deploy (vm-095 lease)
- `db-migrate.sh` (the new migration), the new image; `nonint-check`; SC-03 and SC-07 once each: the hypotheses, the ruled-out cause
  and the ranking visible in the UI.

## Out of scope

Case similarity and a prior from confirmed incidents (T-0048 first); external knowledge (ACR-0022); actions (ACR-0019).
