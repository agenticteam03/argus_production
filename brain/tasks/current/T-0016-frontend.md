# T-0016 — The web frontend (`frontend/`), test-driven

| Field | Value |
|---|---|
| Status | `in progress` — steps 1–2 started 2026-10-06, **before T-0015 merged** (deviation: the UI is mock-only and needs nothing from `contracts/` yet; the HTTP/contract work still waits for T-0015) |
| Phase | 10 — output modes |
| Architecture | ACR-0001 (from T-0015) |
| Branch | `task/T-0016-frontend` (one PR per step is fine) |
| Owner | `juanes6554` (guidelines and design) + agent (tests first, then code) |
| Needs the VM lease | only for the deployment step |

## How to start

`juanes6554` tells his agent **"I want to implement the frontend"**. The agent follows
[`../../agents/AGENT_PROTOCOL.md`](../../agents/AGENT_PROTOCOL.md) §1 (onboarding with
[`../../../START_HERE.md`](../../../START_HERE.md) first if `brain/developers/juanes6554.md` does not exist), reads
this file and [`T-0015-ui-read-access.md`](T-0015-ui-read-access.md), explains the rules below, and asks for the
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
4. **Token in memory only** (never `localStorage`, cookies or the URL); request `scope=read` at login; API text
   is shown as text (no raw HTML), so log lines cannot inject scripts.
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
- **2026-10-06 — review of PR #24 (`conantkd`): the prototype aligned with ACR-0001 (UIs read-only):**
  - **red:** 11 of 27 unit tests failed for the right reasons: the roles were `admin`, not `approver`; the menu
    had approvals, agent, simulator and scheduler pages and filtered by role; the login used emails and returned
    no `/me` shape; the Argus port offered `askAgent` and `decideApproval`;
  - **green:** 27/27 (`parseRunbook` 11, `routes` 7, `mockAuthAdapter` 7, `mockArgusAdapter` 2) and `vite build`.
    The agent chat, the approvals card and the health card are removed; the dashboard says the UI is read-only;
    login by username; the menu follows the `/me` actions; `GUIDELINES.md` updated to match.
