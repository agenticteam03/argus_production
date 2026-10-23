## 2026-10-22 - T-0049 S3b: the add-capability skill

Type: implementation
Who: juanbetancurm (+ agent)
Context: T-0049 step S3, the second P1 skill (`add-capability`), taken over from S2's plan when its session ran out
of quota. Worktree `w-s3b`, branch `task/T-0049-s3b-add-capability` from main `6a72339`. The pattern comes from
T-0036 to T-0040 and T-0047 H5 (`analysis.anomaly_summary`).
Decision / result:
- `.claude/skills/add-capability/SKILL.md`: the lifecycle of a new read. Test first; then the `CapabilitySpec` in
  `build_catalog()` (read safety class, level, a tag of its own, `ALLOWED_FIELDS` for a sensitive read);
  `max_per_incident` in `config/policy.yaml`; the executor and its inputs in wiring and replay's `FixtureExecutor`.
  The read starts **offered to no class**. The offer is a separate change with its own model batch (ACR-0024 §3.8,
  as #274). A read that changes the design needs an accepted ACR first.
- `scripts/check_capability.py <name>` (read-only) lists every missing piece. The pieces: in the catalog; snake_case
  unique `model_name`; non-empty `description` and `use_when`; level 1-3; a read safety class; `allowed_fields` when
  sensitive; a tag; target kinds; a positive integer `max_per_incident`; a known executor consistent with `runs_in`;
  replay can answer it; no class offer; a test names it. `--all` checks the structure of every committed read.
  `--allow-offer` is for the offer change only.
- Found on the way: `argus/policy/engine.py` reads a missing `max_per_incident` as 10, so a forgotten limit does not
  fail at startup. The checker requires it. Every committed read has one today (`--all` passes).
- Not checked by the script: that the result is correct, minimal or free of a cause; the read's own tests and the
  reviewer judge that. Two older reads (`container.events`, `metrics.restart_history`) are named by no test;
  `--all` does not require that, single-name mode does.
Consequences: `.claude/skills/` is protected: conantkd reviews. No runtime change.
References: [T-0049](../../tasks/current/T-0049-agent-skills.md), ACR-0024, ACR-0028, #274.

### Test state

- **RED seen:** against a naive checker that only looked the name up in the catalog, **23 failed, 3 passed**: a
  missing or bad `max_per_incident` (six forms), an initial class offer, a sensitive read without allowed fields,
  twelve wrong spec fields, an executor replay cannot answer, a read no test names, and the CLI.
- GREEN: `tests/skills/test_add_capability.py` **26 passed**. Running `--all` twice on the committed repository gives
  the same PASS (read-only, idempotent). `analysis.anomaly_summary` passes, and `container.status` fails as offered
  unless `--allow-offer`. Ruff clean.
- Full offline suite on `6a72339` plus this change: **1658 passed, 62 skipped, 1 deselected in 964 s**, exit 0 (the
  known detached-CI Brain test). Brain lint clean.

### Next step

S1 pre-reviews; conantkd reviews the PR (protected path). Then S3c `db-migration`.
