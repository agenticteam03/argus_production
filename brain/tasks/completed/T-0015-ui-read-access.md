# T-0015 — Read access for user interfaces (API side)

| Field | Value |
|---|---|
| Status | `done` 2026-10-07 (steps 1-5 merged in PR #22, ACR-0001 accepted; step 6 proved on vm-095, PR #35) |
| Phase | 10 — output modes ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | §7.1 (HTTP API), §17.3 (authentication), §25 OD-10 ("dedicated UI: not needed for this release") → ACR first |
| Branch | `task/T-0015-ui-read-access` |
| Owner | `juanbetancurm` (+ agent) |
| Needs the VM lease | only for step 6 |
| Unblocks | [`T-0016-frontend.md`](../current/T-0016-frontend.md) (`juanes6554`'s frontend) |

## Goal (plain language)

Argus has one door, its HTTP API. The console (`argus diagnose …`) is one visitor; a web frontend will be another.
The operator uses whichever they prefer, or both. This task prepares the door for a frontend that may only
**read**, and makes that rule part of Argus itself, so no bug in a frontend can start, approve or change anything.
It also writes down the exact data the frontend may rely on, so later core changes cannot break it silently.

## Steps (tests first in each step)

1. **ACR-0001 (OD-10).** "Dedicated user interfaces are allowed as separate clients of the HTTP API. A UI token
   can be limited to read access. The team's web frontend lives in `frontend/` and runs as `argus-v18-ui` (static
   files + a proxy to the API) on a loopback port of vm-095." Adds `GET /api/v1/me` and the read-only token to §7.1
   and §17.3. Not a safety principle: it narrows access, adds no write path and no public port.
2. **Read-only tokens.** The login form already carries the OAuth2 `scope` field. `scope=read` gives a token
   with `access: read`; every route that is not a `GET` refuses it with 403, whatever the user's role. Red first:
   `POST /api/v1/investigations` with a read token → 403; the same user's full token still works; every `GET`
   still works with a read token.
3. **`GET /api/v1/me`.** Who is logged in: user, role, `access` (`read` or `full`), and the list of **actions**
   this token may use (today: `view_incidents`, `view_timeline`, plus `view_evidence` for operator/approver).
   A frontend shows a button only when its action is in this list: later features add actions here, not new
   permission logic in the frontend.
4. **Browser access for development.** Setting `ARGUS_UI_ORIGINS` (comma-separated, e.g.
   `http://localhost:5173`). Empty by default: no CORS headers, nothing changes. Test both.
5. **The UI contract.** `docs/API-FOR-UI.md` (login, me, incidents, detail, events, evidence, escalations, with
   example JSON) and `contracts/ui-api.json`: the OpenAPI schema of exactly those routes. A test compares the
   running API with the snapshot: a change that would break the frontend turns CI red for whoever made it, and
   updating the snapshot is a deliberate, reviewed act. The same test regenerates sample responses
   (`contracts/samples/*.json`, from a scripted SC-03-like run) that the frontend's tests use as their fake API.
6. **Deploy and prove (VM lease).** Deploy on vm-095, rebuild the agent; through the SSH tunnel: a read token reads
   the incidents and is refused on `POST /api/v1/investigations` (403); NO INTERFERENCE.

## Acceptance criteria

Full suite green (offline + Postgres in CI); red seen for steps 2–5; ACR accepted and applied; the evidence of
step 6 archived; Brain updated (`CURRENT_STATE.md`, `tdd/CURRENT_TEST_STATE.md`, journal).

## Red seen / evidence

- **Step 1 (2026-10-06):** ACR-0001 drafted ([`../../architecture/changes/ACR-0001-ui-read-access.md`](../../architecture/changes/ACR-0001-ui-read-access.md)) and applied to `ARCHITECTURE.md` as v1.8.1 on this branch (§2.4, §7.1, §17.3, §25 OD-10, changelog). Status `proposed` until a teammate approves the PR. Design notes: the read-only flag is a new JWT claim `access`, separate from the existing `scopes` claim (target scopes); three read routes the code already serves (`/events`, `/evidence/{id}`, `/escalations`) were missing from §7.1 and are now documented.
- **Steps 2-4 (2026-10-06):** `tests/test_ui_access.py`, 10 tests. Red seen for each step before the code:
  step 2, the login ignored `scope=read` (no `access` claim) and `POST /api/v1/investigations` with a read token
  returned 202; step 3, `GET /api/v1/me` returned 404; step 4, `Settings` had no `ui_origins`. Code: the read-only
  check sits in the one principal dependency (`argus/adapters/inbound/http.py`), so every route, including future
  ones, is covered; the test walks all registered non-GET routes. A token without the `access` claim (issued before
  this change) counts as full. Refusals are audited as `access.read_only_refused` (incident-less audit row).
- **Step 5 (2026-10-06):** `tests/test_ui_contract.py`, 3 tests; `contracts/ui-api.json`, `contracts/samples/*.json`
  (7 files), `docs/API-FOR-UI.md`. Red seen: the contract and the 7 samples were missing. The snapshot guards paths,
  parameters, authentication and the login form; the read routes declare no response models, so the samples guard
  the response shapes (keys and value types). Regenerate with `ARGUS_UPDATE_UI_CONTRACT=1`. Samples never hold a
  usable token.
- **How the tests ran:** Windows Smart App Control on the main laptop blocks a native LangGraph dependency
  (`uuid_utils`), so the offline suite ran in Docker (`python:3.12`, repository mounted): **81 passed, 5 skipped**
  (the Postgres tests; CI runs them).
- **Step 6 (2026-10-07): proved on vm-095.** No deploy and no rebuild: the running agent image already carries
  T-0015. Through the loopback API: `scope=read` login → a token with `access=read`; `GET /api/v1/me` → operator,
  `access=read`, `view_incidents,view_timeline,view_evidence`; `GET /api/v1/incidents` → 200; `POST
  /api/v1/investigations` → **403**; no token → 401; NO INTERFERENCE.
  [Evidence](../../execution/history/T-0015/step-06/evidence.md).
