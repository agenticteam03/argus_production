## 2026-10-21 — T-0016: incident metric charts on ECharts (plan 08, F3) and a visible Refresh

Type: frontend
Who: juanes6554 (+ agent)
Context: the hand-rolled SVG charts showed no thresholds, events or zoom; the ui-graphs prototype and
`08-frontend-plan-new-ui.md` (F3) describe the target. The API already serves every field (ACR-0017, ACR-0021,
T-0045 B7).
Decision / result: `frontend/src/components/charts/` replaces `MetricChart.jsx`: `chartOptions.js` (pure, unit-tested)
builds each ECharts option with the alert and warning lines (`direction` above or below), the baseline band, the
incident band (at least 8 px), the fired signal in red from the incident start, and an event lane; `MetricChart.jsx`
owns one SVG-rendered instance; `ChartGrid.jsx` links every chart of a page (drag, Ctrl + scroll, toolbar zoom, Focus
incident, Reset zoom, ranges from `ranges_available`). ECharts (6.1 since the merge with `main`: 5.x had
GHSA-fgmj-fm8m-jvvx) is bundled by Vite and lazy-loaded (initial chunk
unchanged at 221 KB gzipped; charts 189 KB on demand). Each chart's badge explains itself on hover (`Hint` in
`ui.jsx`). The Refresh button keeps spinning at least 600 ms and shows a toast with the result.
Consequences: ECharts' inside zoom swallows every wheel event, so plain wheel events are kept from it to let the page
scroll; the chart and "No data" blocks carry distinct React keys because ECharts empties its node on dispose.
References: [T-0016](../../tasks/current/T-0016-frontend.md), `frontend/GUIDELINES.md`.

### Test state

Frontend: Vitest 191 passed (chartOptions, refresh and format tests seen red first), Playwright 25 passed, ESLint 0
errors.
