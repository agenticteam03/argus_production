## 2026-10-23 — T-0016: the security keys page in the app's style, light and dark

Type: frontend
Who: juanes6554 (+ agent)
Context: `/account/security` (#284, PHASE-16 step 3b) arrived after the T-0016 redesign (#294) and still had its own
look: a smaller title, doubled card padding, errors and results as bare text, no state badge.
Decision / result: `frontend/src/pages/Security.jsx` uses only theme tokens and the shared pieces (`Card` with an icon
title, `Pill` for the login's state, `InsetRow` for each key, tinted alert and notice boxes, a styled `code`), so it
follows the light and dark themes like the other pages. The form's grid fits its field count. Behaviour, ceremonies
and texts are unchanged.
Consequences: none for the API or the VMs; the UI on vm-095 shows it after the next deploy.
References: [T-0016](../../tasks/current/T-0016-frontend.md), #284.

### Test state

Frontend: Vitest 298 passed (the two new Security tests seen red first), ESLint 0 errors on the changed files.
