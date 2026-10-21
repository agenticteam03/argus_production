## 2026-10-21 — T-0016: login without the picture, times in the browser's zone

Type: frontend
Who: juanes6554 (+ agent)
Context: the login's hero photo looked out of place, above all in the light theme, and the UI hard-coded Colombia
time (COT) for everyone.
Decision / result: the login is the form alone, centred, in both themes; `public/images/argus-hero.jpg` and its CSS
are removed (the real-mode build test checks that no photo is shipped). Times use the browser's time zone and always
name it (`zoneLabel` in `utils/format.js`: COT for Colombia, the Intl abbreviation such as EST or UTC, else the GMT
offset); `clockCot` became `clockZone`, and Playwright pins `America/Bogota` so the e2e label stays stable. The
favicon now points at the existing `/images/argus-logo.svg`. The developer profile records Spanish and both agents.
Consequences: none for the API or the VMs.
References: [T-0016](../../tasks/current/T-0016-frontend.md), `frontend/GUIDELINES.md`.

### Test state

Frontend: Vitest 165 passed (format and build tests seen red first), Playwright 25 passed, ESLint 0 errors.
