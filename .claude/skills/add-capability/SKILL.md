---
name: add-capability
description: >-
  Add a new read capability to Argus (a CapabilitySpec in the catalog, its
  policy limit, wiring, replay support and tests), offered to no incident
  class. Use when asked to "add a read", "add a capability" or "a new tool for
  the model"; not for offering an existing read to a class.
---

# Add an Argus read capability

Read `brain/architecture/ARCHITECTURE.md` §12 (capabilities, levels, safety
classes) and the task's own file first; they win over this skill. A read that
changes the design (a new executor, a new kind of data, a new gateway route)
needs an accepted ACR first (`acr-and-version-line`). This skill grants no
permission to commit, push, deploy, or offer the read to a class.

The pattern follows T-0036 to T-0040 and T-0047 H5 (`analysis.anomaly_summary`).

1. **Test first.** Add `tests/test_<task>_<read>.py` that names the read by its
   canonical name and asserts its spec, its policy limit and that no class offers
   it (see `tests/test_t0047_h5_anomaly_summary.py`). Show it failing.
2. **Spec.** In `argus/capabilities/catalog.py`, write the implementation and a
   `CapabilitySpec` in `build_catalog()`:
   - a canonical `name` and a unique snake_case `model_name`;
   - `description` and `use_when` written for the model;
   - an args model and the target kinds (`container`, `host`);
   - level 1-3 and a read safety class (`READ_ONLY_SAFE` or `READ_ONLY_SENSITIVE`);
   - a tag of its own and its executor.
   A sensitive read lists the value paths it keeps in `ALLOWED_FIELDS` (ACR-0028).
   The result says facts with numbers and never names a cause.
3. **Tag.** Use a tag no class has. A tag a class already has (`container`,
   `cpu`, ...) offers the read at once. Adding the read to a class is a
   separate change with its own model batch: accuracy not lower per class and
   hard 0, before it merges (ACR-0024 §3.8; #274 is the example).
4. **Policy.** Add `config/policy.yaml` `capabilities: <name>: {max_per_incident: N}`
   with N ≥ 1, plus a comment naming the task and "offered to no class yet".
   A missing entry refuses the read. A missing `max_per_incident` silently
   becomes 10 in `argus/policy/engine.py`, which is why the checker requires it.
5. **Wiring and replay.**
   - A read through a target gateway uses an executor in
     `argus/infrastructure/wiring.py` `EXECUTOR_KINDS`.
   - An in-worker read uses `argus_internal` with `runs_in="worker"`; so does
     a combined read (`max_subcalls > 0`).
   - When the executor client needs new inputs (as H5's `lines` and
     `class_signals`), pass them in both `build()` and `tools_dispatcher()`, and
     in `argus/evaluation/replay.py` to `FixtureExecutor`. Without that, the
     model batch cannot replay it.
   - An eval case that should exercise the read needs its answer under the
     executor's `fixtures`.
6. **Check.** From the repository root:
   `python .claude/skills/add-capability/scripts/check_capability.py <name>`
   Status 0 means none of the listed problems was found. `--all` checks the
   structure of every committed read. `--allow-offer` is only for the separate
   offer change. Then run the focused tests, the full offline suite, Brain
   lint, a journal entry and the commit block (`code-bash-step`).

The checker is read-only and static. It covers the pieces it lists:

| Area | What it checks |
|---|---|
| Spec | in the catalog; snake_case `model_name`, unique; `description` and `use_when` not empty; level 1-3; a read safety class; a tag; valid target kinds |
| Sensitive reads | `allowed_fields` present |
| Policy | positive integer `max_per_incident` |
| Executor | the executor is known; in-worker reads (and combined reads) are consistent with `runs_in`; replay can answer a gateway read |
| Offer | no initial class offer |
| Tests | some test names the read |

It does not judge whether the result is correct, minimal or safe to show:
the tests and the reviewer do.
