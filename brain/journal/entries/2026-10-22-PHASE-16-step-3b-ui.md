## 2026-10-22 - PHASE-16 step 3b: the UI's security keys page (enrol, confirm the login, step-up)

Type: work (frontend)
Who: conantkd (+ agent)
Context: step 3a (#280) built the WebAuthn ceremonies in the API. A person needs a screen to register their keys and
complete a login with one; phase 17's approvals will need the step-up from the browser.
Decision / result:
- `src/services/webauthn.js`: the JSON-to-bytes conversion of the API's options for `navigator.credentials.create` /
  `.get`, and the credential back to JSON. Nothing is decided in the browser.
- `src/services/secondFactorAdapter.js`: `status()` (from `/me`), `credentials()`, `enrol({ticket | stepUpToken,
  label})`, `confirmLogin()`, `stepUp(object)`. The authenticator is a parameter, so tests pass a fake one. The demo
  (mock) adapter says the second factor is not configured. `apiFetch` keeps the API's short refusal reason
  (`err.detail`), so a refused ceremony says why.
- `/account/security` (`src/pages/Security.jsx`), linked from the account menu only when `/me` lists
  `manage_second_factor`:
  - the first key with another administrator's code (D4);
  - confirming this login with a key;
  - a further key after a step-up of an enrolled one (D3's two keys);
  - errors and results announced (`role="alert"`, `role="status"`); a browser without WebAuthn is told so.
- The contract test now runs the five second-factor calls against `contracts/ui-api.json`.
Consequences: the step-up's other uses (an approval, a hold) come with phase 17's screens. This branch sits on step
3a's; it is retargeted to main once #280 merges.
References: [PHASE-16](../../tasks/current/PHASE-16-operator-access.md), #280, ACR-0018.

### Test state

PHASE-16 step 3b: Vitest 219 passed (18 new: `webauthn.test.js` 5, `secondFactorAdapter.test.js` 8,
`Security.test.jsx` 5; the contract test covers the new calls); coverage floors hold; ESLint 0 errors (the 23 known
react-refresh warnings); `npm run build` passes.
