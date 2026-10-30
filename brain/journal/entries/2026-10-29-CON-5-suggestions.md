## 2026-10-29 - CON-5: suggestion cards with Insert and Copy (ACR-0043)

Type: feature (frontend)
Who: conantkd (+ agent)
Context: the operator console board ([OPERATOR-CONSOLE](../../tasks/current/OPERATOR-CONSOLE.md)) asks for suggestions with
Insert and Copy, `suggestion_id` and an "Applied" state after CON-3 (#403). CON-2 (#404) and CON-4 (#406) are open PRs:
#404 stores an optional `suggestion_id` (at most 64 characters) with each command, #406 sends one suggestion per analysis as
`{command, command_id}`.
Decision / result:
- [`argus-console-mockup-spec.md`](../../tasks/current/argus-console-mockup-spec.md) §7: where suggestions come from, the
  client id (`sug-<command_id>` when the API sends none), registry-only validation, Insert never runs, "Applied" from history.
- `frontend/`: a **Suggestions** card in the Argus panel (`ConsolePanel.jsx`) with "Insert into console" (fills and focuses the
  input) and "Copy". The terminal sends `suggestion_id` only for an unedited inserted command, and keeps it through the `yes`
  of a write. The logic is `isRegistryCommand`, `suggestionsFrom`, `appliedIds` and `suggestionIdFor` in
  `utils/consoleSession.js`.
- The offline demo adds an analysis with a suggestion to `cache status` (suggests `cache restart`) and `api cpu` (suggests
  `cache status`), and stores `suggestion_id`. No HTTP console call is added: the real adapter gets them in CON-2.

Consequences: if #406 adds an `id` or a `rationale` to the suggestion, the cards use them as they are. If CON-4 sends several
suggestions per analysis, `suggestionsFrom` needs to read a list.

### Test state

Red seen first: the new `consoleSuggestions` and demo tests failed (8) before the code, and two of the three new panel tests
failed before the card. Then: Vitest 63 files / 383 tests passed, ESLint no errors, `vite build` passed, all 32 Playwright
tests passed. Checked by hand in demo mode with Playwright at 1280x720: `cache status` shows a `cache restart` card, Insert
fills the input without running it, Enter and `yes` mark the card "Applied"; no horizontal scroll.

### Next step

CON-2 and CON-4 merge; then the HTTP adapter's console calls carry `suggestion_id` with the rest of CON-2.
