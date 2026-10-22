# T-0047 — Explicit hypotheses and a transparent cause ranking

| Field | Value |
|---|---|
| Status | `in progress` — [ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md) accepted (#215); H1 merged (#228); H2 merged (#236); H3 merged (#237); both deployed on vm-095 (#239); H4 step 1 (the metrics) merged (#245); H5 step 1 (`analysis.anomaly_summary`, offered to no class) merged (#252); H5 step 2 part A (per-target range fixtures in the replay) merged (#267); part B (the read offered to two classes) in review (#274), its model batch run before the merge ([evidence](../../execution/history/T-0047-H5B/step-01/evidence.md)) |
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
  - Step 2, part B (built, batch run 2026-10-22, in review): the `anomaly` tag on `dependency_unavailable` and `container_restart_loop`
    (a class-registry change: `conantkd` reviews). The offline evaluation of `tests/eval/cases` is unchanged
    (registered 32/61, `--strategy baseline` 57/61, hard 0): the baseline asks no model, so a tool offer changes nothing
    without one. The model batch decides whether the offer stays: the 12 cases of the two classes (`dep-*`,
    `ambiguous-dep-all-running`, `restart-*`) in their own folder on vm-095, `--strategy model_loop` (the registered
    strategy of `container_restart_loop`; `dependency_unavailable` runs `baseline`, D-003, which asks no model),
    5 trials, before (main: the read registered but offered to no class) and after (this branch), run **before the
    merge** (ACR-0024 §3.8: a read is offered to a class only when its batch improves it); accuracy not lower per
    class and hard 0, else the tag is removed. vm-095 runs afb72e8 (#271), which has H5 registered, so no image is
    built: both runs use the deployed image with a read-only bind of a `git archive` of `argus/` over `/app/argus`
    (main's for "before", this branch's for "after"; they differ only in `classes.py`). That deviates from
    `ops/eval-run.sh`, which takes no extra mount: the block runs its `docker run` line plus that one mount, and
    prints both lines side by side. A build would be deploy work (`conantkd`'s lane) and add build differences.
    **Batch result** (vm-095, run stamp `20261022T174900`, before = main `95e67a7`, after = `b3cc16c`; 60 runs per
    arm): `container_restart_loop` 0.97 → **1.00** (worst trial 0.83 → 1.00), hard 0 → 0; `dependency_unavailable`
    0.52 → **0.84** (worst trial 0.40 → 0.60), hard 0 → **1**; all 60: 0.76 → 0.93, top-1 0.86 → 0.96.
    - The read was called in only 3 of the 60 after-runs (2 dependency, 1 restart). The gain cannot be put down to
      its output alone: the offer also changes the tool list the model sees, and 25 runs per class leave room for
      variance.
    - The one hard (`unsupported_root_cause`): `dep-backend-stopped`, trial 1. The right target and class, but no
      observation of the backend cited. It is the evidence gap that `problems 0.45` shows in both arms. The same case
      scored the same hard on main's code in a first batch that was lost (trial 2).
    - By the letter of the rule, restart keeps the tag. Dependency improves its accuracy but has hard 1, so the
      reviewer decides: keep it, with that explanation, or remove its tag.
    - `dependency_unavailable` runs `baseline` (D-003), so its offer reaches the model only if OP-013's proposal
      gives the class a model strategy again.

### H6 — Deploy (vm-095 lease)
- `db-migrate.sh` (the new migration), the new image; `nonint-check`; SC-03 and SC-07 once each: the hypotheses, the ruled-out cause
  and the ranking visible in the UI.

## Out of scope

Case similarity and a prior from confirmed incidents (T-0048 first); external knowledge (ACR-0022); actions (ACR-0019).
