# OP-001 — Runbook detector metadata alignment

**Owner:** `conantkd` · **Branch:** `task/OP-001-runbook-detectors` · **PR:** #44 · **Status:** code complete; fast-track review.

## Goal

Make the `detector` metadata of every RB-001–RB-021 runbook name the primary incident class assigned to it in
architecture §1.3. RB-001 and RB-008 both map to `container_restart_loop` because they describe different causes
within the same symptom class.

## Work

1. Add a test that derives the expected ID-to-class map from architecture §1.3 and compares it to every runbook's
   YAML metadata. Red was observed before the metadata edits.
2. Update the 18 runbooks with incorrect or empty values; bump their patch versions and `last_reviewed` dates. The
   three already correct runbooks stay unchanged.
3. Update the index with a detector-class column and a v1.1.1 metadata revision; check the index against the same
   architecture map.
4. Run the mapping, knowledge, and SC-04 tests, Brain audit/lint, and CI. The local Windows full suite passes with
   pytest's temporary directory outside the Git worktree; nine Docker/Linux/Postgres tests are skipped locally, and
   Linux CI passes including Postgres. No VM action is required.

## Limits

All runbooks remain `draft` with `last_tested: null`. This metadata change does not register or enable new incident
classes and does not alter the architecture or safety policy.
