## 2026-10-22 - Frontend tests for the shared UI pieces, the runbook card and the incident row; floors raised

Type: tests
Who: conantkd (+ agent)
Context: after #248 the shared primitives (`ui.jsx`), `RunbookCard` and `IncidentRow` still had no unit test.
Decision / result:
- New test files only, rendered with `renderToStaticMarkup` as before; no component changed.
- `ui.jsx`: status and outcome badges (an unknown or missing value is shown as such, never as a known state; only a
  running incident pulses), the live pill (demo data labelled; pulses only while live; its clock in a readable colour,
  the OP-014 step 12 fix), a dash for a missing fact, one pressed segment, tabs with one selected and a roving
  tabindex, a panel only for the selected tab, an alert with Retry only when it can retry.
- `RunbookCard`: mutating tools listed first so a risky step is never hidden behind "+N more"; missing tools counted
  (singular and plural); placeholders instead of blank fields. `IncidentRow`: the link, a queued incident is
  "Waiting to start", class and strategy hidden in the compact card.
- Red seen: listing tools unsorted and putting back `text-muted/60` each fail their test. 175 to 193 tests.
- Coverage: lines 43.6 to 45.4 %, branches 40.9 to 44.4 %; floors 45 / 44 / 41 / 44.
Consequences: pages and hooks remain covered by Playwright only.
References: [OP-014](../../OPEN_PROBLEMS.md), #248.
