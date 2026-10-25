## 2026-10-23 — T-0049 R1: closed precedents in the evaluation cases, so `knowledge.prior_incidents` can be measured

Type: tests
Who: juanbetancurm (+ agent)
Context: R1 compares planned reads offered to a class against the class as it is, on the same cases. Item 5 of the
R1 ranking: T-0039's `knowledge.prior_incidents` could not be measured. A replay's store holds only the incident
being investigated, and no case seeded a closed precedent for the same target and class. So the read always answered
"no prior closed incident".
Decision / result:
- `argus/evaluation/cases.py`: an optional `prior_incidents:` list in a case. Each entry has `class`, `target`,
  `diagnosis`, `root_cause` and `closed_at`, plus optional `outcome`, `confidence` and `findings`.
  - Unknown keys are refused.
  - The class must be registered, and the targets must parse.
- `argus/evaluation/replay.py`: `seed_prior_incidents` stores them as closed incidents before the run, opened five
  minutes before `closed_at`. A case without them leaves the store as before.
- Three cases are seeded, each with the same target and class as the case:
  - `restart-oom-01`: two helpful precedents (OOM kills at the same 64 MiB limit);
  - `dep-cache-paused`: one helpful precedent (the cache was paused before);
  - `restart-crash-01`: one **misleading** precedent. It records an OOM kill, while this case is a non-OOM crash
    (exit code 1, `oom_killed` false). A run that trusts history over the evidence says OOM, and its label
    (`diagnosis_any`: non-OOM, exit) fails it.
- No class change: the read stays offered to no class (`config/policy.yaml`, the T-0039 test).
- `tests/eval/README.md` documents the field.
- `tests/test_t0049_r1_prior_incident_fixtures.py` (red first: 5 failed):
  - the format and its refusals;
  - the seeded cases;
  - a seeded case's read returns its seeds, with the read offered for the test only;
  - an unseeded case still finds none;
  - the labelled and seeded cases replay as before while no class offers the read.
Consequences: the batch these fixtures enable is R1's arm for `knowledge.prior_incidents`.
- The cases: the three seeded ones, plus unseeded cases of the same classes as controls (`restart-*`, `dep-*`).
- Arms: control = the classes as registered; offered = the `prior_incidents` tag on `container_restart_loop` and
  `dependency_unavailable` (an archive bind, as #274). `--strategy model_loop`, 5 trials.
- Record: accuracy per class; hard 0; whether the read is called; and, on `restart-crash-01`, whether the offered arm
  says OOM (over-trusting history).
- The offer stays only if accuracy per class is not lower and hard is 0, and the misleading case is not worse.
  The class change is `conantkd`'s review.
References: [T-0049](../../tasks/current/T-0049-agent-skills.md) (R1),
[T-0039](../../tasks/current/T-0039-prior-incidents.md).

### Test state

T-0049 R1 prior-incident fixtures: `tests/test_t0049_r1_prior_incident_fixtures.py` 5 passed (red seen: 5 failed);
`tests/test_t0039_prior_incidents.py` and `tests/test_evaluation.py` pass with it. Full offline suite, with Git Bash
first on PATH: **1862 passed, 34 skipped, 1 deselected** (the known detached-CI Brain test), exit 0.
That ran on `8b40610`; on main `201cc7c` the fixture, T-0039 and evaluation tests: 110 passed.

### Next step

T-0049 R1: review of the prior-incident fixtures; then the batch above, with the other R1 arms.
