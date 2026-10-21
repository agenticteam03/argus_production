## 2026-10-21 - T-0047 H4: a listing no longer counts as observing every container

Type: fix
Who: conantkd (+ agent)
Context: #245 (H4 step 1) counts a target as observed when an `ok` observation on its host names it, so the
`pg-leaker-*` diagnoses (named by `database.health`'s sessions) are not `unsupported_root_cause`. Raised in its review:
`container.list` names every container of its host, so one listing made every target on that host "observed" and the
hard check could never fire there. #245 merged before the change.
Decision / result:
- `NAMING_CAPABILITIES = {"database.health"}` in `argus/evaluation/replay.py`: only those reads' values name other
  targets. A new test: a `container.list` naming the cache leaves it unobserved and its diagnosis
  `unsupported_root_cause` = 1. Red seen against main's code. The baseline cases still give 0.
Consequences: a new capability whose values describe another target is added to the set, with a case.
References: #245, [T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md).
