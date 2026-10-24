## 2026-10-23 — T-0016: incident pages failed in the deployed UI (ECharts registration dropped by the build)

Type: bug fix
Who: juanes6554 (+ agent)
Context: on the deployed UI every incident page showed "This page couldn't be displayed"; the console said
`TypeError: La[a] is not a constructor` inside the charts chunk. The dev server (`npm run dev`) was fine.
Decision / result: root cause found in a local production build (`vite build` + `vite preview`, mock mode, same
error). `frontend/package.json` declares the app's modules free of side effects (`"sideEffects": ["**/*.css"]`, step
4b, so a real build drops the mock code). The build therefore dropped the top-level `register([...])` of
`src/components/charts/echarts.js`, the call that installs ECharts' SVG renderer and components; zrender's painter
table was empty and `new painterCtors[renderer]` threw. The dev server does not tree-shake, so it never showed.
The fix registers on first use inside the exported `init` and `connect`, which a build keeps; `"sideEffects"` stays
as it is. The charts chunk grows from 305 KB to 590 KB: the renderer and components were missing before.
Lesson: with `"sideEffects"` in `package.json`, a module whose only job is a top-level call is silently dropped from
a production build; do such work inside an exported function.

### Test state

Frontend: `src/build.test.js` now also requires ECharts' `registerPainter` in a real-mode build: red seen
(`expected ... to contain 'registerPainter'`), green after the fix. Vitest 298 passed (46 files); ESLint clean on the
changed files. Browser: the production build (`vite preview`) shows an incident's Metrics tab with 3 SVG charts and
no console error from the new chunk.

### Next step

After the merge, deploy the UI on vm-095 (lease, `code.bash`) and check an incident page on the public UI.
