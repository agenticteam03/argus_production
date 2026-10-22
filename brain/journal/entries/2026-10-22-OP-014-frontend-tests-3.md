## 2026-10-22 - Frontend tests for the system map's rendering; floors raised

Type: tests
Who: conantkd (+ agent)
Context: `SystemMap.test.js` covers its pure helpers (layout, state, mini pair); the rendering (the map, the Map
tab, the dashboard and incident cards) had no unit test.
Decision / result:
- `SystemMapRender.test.jsx` (8 tests, `renderToStaticMarkup`; no component changed): each box named with its state
  for screen readers (root cause, affected, unknown, Argus); an unknown box dashed; edges drawn only between boxes on
  the map; boxes are buttons only when selectable, one pressed; the mini map shows only the affected target and its
  different root cause with their link, and hides otherwise; the Map tab opens on the root cause and links the
  incident; the dashboard card hides with no components.
- Red seen: boxes always interactive and an edge to a node not on the map each fail (6 tests). 193 to 201 tests.
- Coverage: lines 45.4 to 48.5 %, branches 44.4 to 48.5 %; floors 48 / 47 / 45 / 48.
Consequences: none for the UI.
References: [OP-014](../../OPEN_PROBLEMS.md), ACR-0017.
