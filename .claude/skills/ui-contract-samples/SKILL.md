---
name: ui-contract-samples
description: >-
  Update Argus's UI contract (contracts/ui-api.json and contracts/samples/)
  after an API change, keeping every sample whose shape did not change. Use
  when tests/test_ui_contract.py fails with "the API changed for user
  interfaces" or "changed shape", or when a route a UI uses is added.
---

# Update the UI contract and only the samples that changed

Read `tests/test_ui_contract.py` (its docstring), `docs/API-FOR-UI.md` and
ACR-0001 first; they win over this skill. `contracts/` is a protected path:
the change needs `conantkd`'s review. This skill grants no permission to
commit, push or change the frontend.

1. **Is the change intended?** A red contract test means the API changed for
   user interfaces. Regenerate only for a reviewed change: a new field or
   route that the task or its ACR names. Otherwise fix the code, not the
   contract.
2. **A new route a UI may call:** add it to `UI_ROUTES` in
   `tests/test_ui_contract.py` and describe it in `docs/API-FOR-UI.md` first.
3. **Regenerate, keeping unchanged samples.** From the repository root, run
   `python .claude/skills/ui-contract-samples/scripts/keep_unchanged_samples.py`.

   It runs `ARGUS_UPDATE_UI_CONTRACT=1 python -m pytest tests/test_ui_contract.py`.
   Then it writes back the old bytes of every sample whose shape (keys and
   value types) did not change, and reports:
   - the samples whose shape changed;
   - the samples with the same shape whose values differ beyond ids and
     times (a new action, a new enum value): their old bytes are kept;
   - the new samples;
   - the samples no longer produced.

   It touches only `contracts/samples/` (and the test rewrites
   `ui-api.json`). If the regeneration fails, it puts every sample and
   `ui-api.json` back and removes any sample the run created.
4. **Review the diff.** `git diff contracts/` should show only `ui-api.json`
   and the samples named in the report. A sample that changed without a
   reason in the task is a regression: stop and look. A "values differ"
   sample the task meant to change (a UI step needs the new value): run the
   script again with `--keep-new <name>`, so the frontend tests see it.
5. Run the contract test without the switch (it must pass), the frontend's
   tests (they use the samples as their fake API), the full offline suite,
   a journal entry, then the commit block (`code-bash-step`).

Example: #280 added `second_factor` to `/me`. Only `me.json` should change.
