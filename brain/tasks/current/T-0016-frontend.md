# T-0016 — The web frontend (`frontend/`), test-driven

| Field | Value |
|---|---|
| Status | `in progress` — steps 1–2 merged (PR #24); step 3 (read-only API wiring) merged 2026-10-10 (PR #56); still open: Playwright acceptance tests, the read-only network guard, the `contracts/ui-api.json` check |
| Phase | 10 — output modes |
| Architecture | ACR-0001 (from T-0015) |
| Branch | `task/T-0016-frontend` (one PR per step is fine) |
| Owner | `juanes6554` (guidelines and design) + agent (tests first, then code) |
| Needs the VM lease | only for the deployment step |

## How to start

`juanes6554` tells his agent **"I want to implement the frontend"**. The agent follows
[`../../agents/AGENT_PROTOCOL.md`](../../agents/AGENT_PROTOCOL.md) §1 (onboarding with
[`../../../START_HERE.md`](../../../START_HERE.md) first if `brain/developers/juanes6554.md` does not exist), reads
this file and [`T-0015-ui-read-access.md`](../completed/T-0015-ui-read-access.md), explains the rules below, and asks for the
guidelines (step 1).

## How the work is split

- **`juanes6554` gives guidelines:** which framework (React, Angular, Vue, …), which screens, what each shows,
  what happens on click, the look. He writes them in `frontend/GUIDELINES.md` (plain language is fine).
- **The agent turns every guideline into tests first**, shows them failing ("red seen", recorded below), then
  writes or completes the code until they pass. No frontend code is merged without a test that failed first.
  `juanes6554` may write code himself; it still needs its tests first, and CI enforces them.

## The tests (enforced by CI)

| Kind | Tool | What it proves |
|---|---|---|
| Acceptance (main) | Playwright against the built app, with the API faked from `contracts/samples/*.json` | each guideline, as a user sees it; independent of the framework |
| **Read-only guard** | Playwright network check in every acceptance test | the app never sends anything except `GET` and the login; any other request fails the test |
| Contract | the app's API client is checked against `contracts/ui-api.json` | the app uses only fields Argus promises; a core change that breaks it is caught in the core PR |
| Unit | the framework's own runner (Vitest, Jest or Karma) | components and helpers |
| Lint and build | the framework's linter + production build | the code builds the same way on CI and on the VM |

A CI job `frontend` runs all of them on every push that touches `frontend/` or `contracts/`. A PR with the job red
is not merged (`agents/REVIEW_PROTOCOL.md`: CI green before merging).

**Fast-track (until 2026-10-12):** `juanes6554` may merge his own frontend PRs under the rule in
`agents/REVIEW_PROTOCOL.md` ("Temporary fast-track"): his agent posts the review report, the PR lists itself in
`policies/main-exceptions.txt`, and the jobs `test` and `frontend` are green. Not fast-tracked: the PR that adds the
CI job (it changes `.github/workflows/`) and any change to `contracts/` (shared with the API side).

## Rules against conflicts (now and later)

1. **Own folder:** all frontend code in `frontend/` (its own `package.json`, tests, `Dockerfile`, README). The core
   team never edits it; this task never edits `argus/`. The only shared files are `contracts/` (changed by the API
   side, reviewed by `juanes6554`) and the CI workflow (one job added in step 2).
2. **Only the contract:** the app uses only the routes and fields in `docs/API-FOR-UI.md`. Missing data → ask for
   it as a separate API change (a contract update), never call undocumented routes.
3. **Buttons follow `/api/v1/me`:** the app shows an action only when `/api/v1/me` lists it. New Argus features
   then appear by adding actions on the server, not by rewriting the frontend.
4. **Token out of `localStorage`/cookies/URL** — kept in memory and, so a reload in the same tab keeps the
   session, in `sessionStorage` (`frontend/src/services/sessionStore.js`), bounded by the token's own JWT `exp`;
   request `scope=read` at login; API text is shown as text (no raw HTML), so log lines cannot inject scripts.
5. **Brain:** fill in this file and append to the journal during the task; `CURRENT_STATE.md` and `NEXT_STEP.md`
   only in the last PR; merge `main` into the branch before pushing (never rebase a pushed branch).

## Steps

1. **Guidelines.** `frontend/GUIDELINES.md` from `juanes6554`; the agent reviews it with him and lists the tests
   each guideline becomes.
2. **Skeleton.** The framework project in `frontend/`, the CI job `frontend`, the fake API from
   `contracts/samples/`, and the first failing acceptance test (the login screen) → make it pass.
3. **Screens, one guideline at a time** (expected first ones: incident list; incident detail with outcome, root
   cause, diagnosis, the DETECT → RECALL → INVESTIGATE ⇄ ACT → RECORD timeline, evidence).
4. **Container `argus-v18-ui`** (built files + a proxy of `/api/` to the agent), compose service on vm-095 bound to
   `127.0.0.1:18010`. Deploy, open it through `ssh -L 18010:127.0.0.1:18010 argus-vm095`, show a real incident;
   NO INTERFERENCE.

## Later: from reading to acting (each level is its own task and ACR)

| Level | What the user gets | What Argus adds | Frontend change |
|---|---|---|---|
| 0 Read (this task) | incidents, root cause, timeline, evidence | T-0015 | — |
| 1 Investigate | a "Diagnose this container" button | a token scope that allows `POST /api/v1/investigations` (the console can already do it) | a button shown when `/me` lists `start_investigation` |
| 2 Visual map | the containers of each host, their health and open problems | a read route over the inventory and the latest signals (contract update) | a new screen |
| 3 Fix with approval | "Argus proposes: restart X — Approve / Deny" | write capabilities + the human approval flow (§7.1 approve/deny with `approval_id` + `proposal_digest`); **safety-principle ACR, two approvals** | approve/deny buttons shown when `/me` lists `approve` |

Even at level 3 the frontend never runs commands itself: it only answers a proposal that Argus made, checked and
audited. That is why starting isolated is not a problem: each level adds a route and an action on the server, and
a screen or a button in `frontend/`.

## Red seen / evidence

- **2026-10-06 — integration of the pre-existing prototype (steps 1–2, this pull request):**
  - **red:** `npm test` → exit 1 (`Missing script: "test"`) — no test harness existed;
  - **red:** a `parseRunbook` fixture test failed (`expected +0 to be 2`) — the fixture used mixed-case wording
    instead of the exact `MISSING TOOL REQUIREMENT` marker that real runbooks use; the fixture was corrected to
    match reality and the parser code stayed unchanged;
  - **green:** 20/20 Vitest unit tests (`parseRunbook` 11, `routes` 4, `mockAuthAdapter` 5) and `vite build`
    (313 modules) after the hero image became a 136 KB JPEG (was 3.8 MB PNG);
  - the CI job `frontend` (unit tests + production build) is added in this pull request; it changes
    `.github/workflows/`, so a teammate must approve it (the fast-track excludes it).

- **2026-10-09 — step 3 begins: read-only API wiring (branch `task/T-0016-step3-screens`), from the PR #24 review
  (`juanbetancurm`) and ACR-0001 constraints (`conantkd`):**
  - **red:** `npm test` → 7 failed: the new `session`/`httpAuthAdapter`/`httpArgusAdapter` tests could not load
    their modules (they did not exist), `routes` still returned `admin` instead of `approver` and listed
    `/approvals`, and `mockAuthAdapter` failed on the username / `/me` shape;
  - **green:** 39/39 Vitest (`session` 3, `httpAuthAdapter` 4, `httpArgusAdapter` 6, `fileRunbooksAdapter` 1,
    `index` 2, `parseRunbook` 11, `routes` 6, `mockAuthAdapter` 6) and `vite build` (348 modules);
  - review items done: username login; form-encoded `scope=read` login then `GET /api/v1/me`; memory-only token,
    401 → logout; roles `viewer`/`operator`/`approver` with Approvals/Simulator/Scheduler removed from the menu;
    header shows the name; overview from `GET /incidents`; dev proxy + `fs.allow`; mocks behind `VITE_ARGUS_MOCK`;
    runbooks read from `argus/runbooks/` (`demoRunbooks/` deleted).
  - **still open (not this step):** Playwright acceptance tests, the read-only network guard and the
    `contracts/ui-api.json` contract check; the write features stay mock-only until the new ACR.
  - **committed:** `5ec43cc` on `task/T-0016-step3-screens`, PR **#56** opened 2026-10-09 (fast-track eligible: no
    `.github/workflows/` or `contracts/` change); merged up to date with `main` (`afe84a6`). CI: `frontend` green;
    the `test` job first failed on a Docker Hub unauthenticated pull-rate limit while pulling `postgres:16-alpine`
    (infrastructure, before any test ran) and was re-run.

- **2026-10-13 — connect the two remaining documented read routes (branch `task/T-0016-step3-screens`):**
  - every read route in `docs/API-FOR-UI.md` is now wired: `GET /api/v1/evidence/{id}` (`getEvidence`) and
    `GET /api/v1/escalations` (`listEscalations`) were the only two missing, so they join the HTTP adapter and the
    mock adapter (parity), and `getOverview` now carries real escalations; the Dashboard gains an **Escalations**
    card (target → incident, outcome badge, route, clamped diagnosis). Writes stay mock-only: there is still no
    approve/deny route and `POST /api/v1/investigations` needs a full token (level 1 ACR).
  - **not connected on purpose:** `GET /healthz` (not in the UI contract — the UI must not call undocumented
    routes) and `POST /api/v1/investigations` (a write a `scope=read` token never gets).
  - **tests written (Vitest run deferred):** extended `httpArgusAdapter.test.js` (evidence + escalations + overview
    now asserts two GETs) and added `mockArgusAdapter.test.js` (escalation shape, overview, viewer 403 on evidence).
    `juanes6554` asked to skip the test run this turn to save time, so the red/green is **pending** a `npm test`
    (frontend only) — the record here will be completed before any merge.
  - **green (build only):** `vite build` → 348 modules, no errors (verifies the new imports/JSX compile).

- **2026-10-13 — no-database demo login + a session that survives a reload (`juanes6554`'s request):**
  - **mock login without a database:** the three demo accounts can be replaced from `.env` (`VITE_ARGUS_USERS`, a
    JSON map of username → `{ password, role }`); a bad value or unknown role falls back to the demo accounts, so
    the demo never breaks. Still frontend-only — no `argus/` change, no ACR.
  - **session across a reload, without touching rule 4:** the mock session (user + role, no token) is kept in
    `sessionStorage` up to `VITE_ARGUS_SESSION_TTL_MIN` (default 8 h) and restored on load by `auth.restore()`
    (`mockSessionStore.js`); logout, tab close or the TTL ends it. `httpAuthAdapter.restore()` returns `null`, so
    the real API token stays **in memory only** — rule 4 is exactly as written. Recorded in `GUIDELINES.md`.
  - **tests written (Vitest run deferred, as asked):** added `mockSessionStore.test.js` (save/load/TTL/clear/no
    storage) and extended `mockAuthAdapter.test.js` (`.env` accounts, restore, logout) and `httpArgusAdapter.test.js`
    (`restore()` → `null`). `vite build` still green.

- **2026-10-13 — "is any of this real?" → honest Live pill + a real-API run setup (`juanes6554`):**
  - **finding (no code change needed to be real):** incidents, timelines, evidence and escalations are real today
    with `VITE_ARGUS_MOCK=0` + the vm-095 tunnel; the UI never touches Postgres itself (the API does). The **agent
    chat** cannot be real yet: `POST /api/v1/investigations` needs a full token and only *starts* an investigation
    for a target — no route answers a free-text question. The **health/status card** has no route either (`/healthz`
    is not in the UI contract and returns different data). Both need a new route + contract/samples/guard + an ACR
    (written up in `frontend/README.md`); the chat stays a placeholder until then.
  - **the pill is now honest:** `LivePill` takes `source`/`at`; the new `dataSource` export in `services/index.js`
    (`demo`/`api`) labels mock runs, and `liveLabel` (`utils/format.js`) plus the last-refresh clock make a "Live"
    that is visibly tied to a successful request. Dashboard and Incidents pass both; the runbook library and the run
    timeline are unchanged.
  - **real run wired:** `frontend/.env.local` (gitignored) sets `VITE_ARGUS_MOCK=0`; the tunnel was closed while
    writing (`curl 127.0.0.1:18000` → exit 7), so the live smoke test still needs the tunnel + a real DB login.
  - **tests written (Vitest run deferred, as asked):** `utils/format.test.js` (`liveLabel`) and `index.test.js`
    (`dataSource`). `vite build` green.

- **2026-10-13 — reload keeps the real session; the incidents list pages 30 at a time (`juanes6554`'s request):**
  - **session across a reload, now in real mode too:** `mockSessionStore.js` became `sessionStore.js` and stores
    `{ user, token, expiresAt }`. `httpAuthAdapter.signIn` saves the token, `restore()` puts it back in memory, and
    `signOut`/`401` clear it (`http.js`). Nothing goes to `localStorage`, cookies or the URL. `expiresAt` is the
    earlier of `VITE_ARGUS_SESSION_TTL_MIN` and the token's own JWT `exp`, so a dead token is never restored. This
    is a **deliberate amendment of rule 4** ("in memory only" → "never `localStorage`/cookies/URL; may be in this
    tab's `sessionStorage`"), because the previous turn's mock-only persistence left real mode logging out on every
    reload; rule 4 in this file and in `frontend/README.md` were updated together.
  - **incidents list paging:** `useIncidentList` fetches the newest rows once (up to `INCIDENTS_CAP = 1000`) — the
    API has no `offset` and no total — and the page shows 30 at a time with a **Show more** button; the summary
    gives how many are visible and the real total (`utils/paging.js`, `incidentsSummary`). Adding `offset`/cursor
    and a count to `GET /api/v1/incidents` is recorded as a contract ask in `frontend/README.md`.
  - **tests written (Vitest run deferred, as asked):** `sessionStore.test.js` (renamed; adds the token round-trip
    and JWT-`exp` expiry), `httpAuthAdapter.test.js` (restore puts the token back; signOut clears both), and
    `httpArgusAdapter.test.js` (401 clears the persisted session; the stale `restore()` case removed), plus the new
    `paging.test.js` for `incidentsSummary`.

- **2026-10-13 — the incident page reads again, the status colours breathe, and the deferred Vitest run closes (this PR):**
  - **first the crash, found by `juanes6554`:** on the real API an audit entry's `detail` is a JSON object
    (`AuditRecord.detail: dict[str, JsonValue]`, `argus/domain/model.py`) but a string in the demo fixtures, so
    rendering it directly threw "Objects are not valid as a React child" and, with no error boundary, unmounted the
    whole app — only the page gradient remained. `utils/format.js` now normalises it (`auditDetail` → `text`/`json`/
    `empty`), the audit `detail` renders as text/JSON, and a new per-route `ErrorBoundary`
    (`components/ErrorBoundary.jsx`, keyed on the pathname) keeps a future render error from blanking the app. The
    demo fixtures had hidden the bug; a real-shape sample is used in the tests. (`ae0d595`)
  - **colours (owner: "a little more vibrant, not too much"):** the status shades had been muted a turn earlier to the
    point of looking grey; their chroma is raised (~1.6–1.8×) in the `@theme` block of `frontend/src/index.css` —
    same hues and lightness, still below Tailwind's defaults, so every existing `text-emerald-300` / `bg-amber-400/10`
    / … class is unchanged. (`bdadd25` muted them, `bc21ab2` brings them partway back.)
  - **incident page (owner: "easier to read, without changing too much, match the other pages"):** fact values no
    longer truncate (targets, trigger/policy ids were cut off — `break-words`, `break-all` for the incident id); a
    little more vertical rhythm and hairline dividers inside the Diagnosis card; and each audit entry's JSON `detail`
    now sits behind the same **Details** toggle the evidence list already uses, so the audit trail stays scannable.
    Same cards, tokens and spacing as the other pages; the only new interaction is that toggle. (`bc21ab2`)
  - **red seen:** `npm test` → 1 failed file: `sessionStore.test.js` could not load — `tokenExpiry` was module-private
    in `sessionStore.js` while the test imported it (`TypeError: tokenExpiry is not a function`).
  - **green:** after exporting the helper → `npm test` **12 files / 70 tests passed**, `vite build` → **351 modules**.
    This closes the four earlier 2026-10-13 bullets whose red/green was deliberately deferred to this run.
  - **committed:** `bdadd25`, `ae0d595`, `bc21ab2` (UI), `1c6b7da` (the test fix); `origin/main` merged into the branch
    before pushing. Still open: the Playwright acceptance tests, the read-only network guard, the
    `contracts/ui-api.json` check, and the incident-list `offset`/total contract ask.
