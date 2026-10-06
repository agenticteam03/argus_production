# T-0015 — Read-only incident UI (web frontend over the existing API)

| Field | Value |
|---|---|
| Status | `planned` |
| Phase | 10 — output modes ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)); a third view next to the formatted CLI and `--raw` |
| Architecture | §7.1 (HTTP API), §17.3 (authentication), §25 OD-10 (dedicated UI: "not needed for this release") → needs an ACR first |
| Branch | `task/T-0015-readonly-ui` |
| Owner | `juanes6554` (his proposal), reviewed by the next developer |
| Needs the VM lease | only for step 6 (deployment on vm-095) |

## How to start (developer and agent)

The developer says **"I want to implement the frontend"**. The agent then:
1. follows [`../../agents/AGENT_PROTOCOL.md`](../../agents/AGENT_PROTOCOL.md) §1 (onboarding with
   [`../../../START_HERE.md`](../../../START_HERE.md) if `brain/developers/juanes6554.md` does not exist yet);
2. reads this file, then only the architecture sections named above;
3. explains the goal and the **rules against conflicts** below in plain language, then starts step 1 with
   [`../../agents/STEP_TEMPLATE.md`](../../agents/STEP_TEMPLATE.md). One step per pull request is fine.

## Goal (plain language)

Today a person sees what Argus did only in a terminal (`argus diagnose …`, formatted or `--raw`). This task adds a
small **web page** that shows the same thing: the list of incidents, and for one incident its outcome, root cause,
diagnosis, the step timeline (DETECT → RECALL → INVESTIGATE ⇄ ACT → RECORD) and the evidence. It only **reads**: it
cannot start, approve or change anything. It is another client of the HTTP API that already exists, like the CLI.

## Rules against conflicts (the core team works on T-0014 at the same time)

1. **Read-only.** The page calls only `POST /api/v1/auth/token` (login) and `GET` routes:
   `/api/v1/incidents`, `/api/v1/incidents/{id}`, `/api/v1/incidents/{id}/events`, `/api/v1/evidence/{id}`,
   `/api/v1/escalations`. No `POST /investigations`, approvals or holds. A test enforces it (step 5).
2. **Own folder.** Everything lives in the new folder `argus/adapters/inbound/web/` (static `index.html`,
   `app.js`, `style.css`: an inbound adapter, like the CLI and the HTTP API) and in `tests/test_ui.py`. No build step
   and no Node toolchain, so CI does not change. No external CDN: every file is served by Argus itself.
3. **Two small touch points outside that folder, both in step 2:** a block at the **end** of `build_api` in
   `argus/adapters/inbound/http.py` that serves the folder under `/ui`, and one entry in
   `[tool.setuptools.package-data]` in `pyproject.toml` (`"adapters/inbound/web/*"`) so the files ship inside the
   agent image, like the runbooks (no Dockerfile change). Nothing else outside the folder changes. If one of those
   files changed on `main` meanwhile, merge `main` first and keep both changes.
4. **No API changes.** If the page needs data the API does not return, stop and ask the core team (a separate PR
   by whoever owns the API), instead of changing the API inside this task.
5. **Shared Brain files at the end only.** During the task, write in this file (Red seen / evidence) and append to
   the journal. `CURRENT_STATE.md` and `NEXT_STEP.md` change only in the last pull request. Always merge `main` into
   the branch before pushing (`git merge origin/main`), never rebase a pushed branch.

## Security (from the architecture, unchanged)

- Same port and listener as the API: `127.0.0.1:18000` on vm-095 (loopback only). People reach it through an SSH
  tunnel from their laptop: `ssh -L 18000:127.0.0.1:18000 argus-vm095`, then `http://127.0.0.1:18000/ui/`.
- Login with the existing users (JWT, 30 minutes). Keep the token **in memory only** (a JavaScript variable), never
  in `localStorage`, cookies or the URL. On 401: back to the login form.
- Show what the API returns; the API already decides what each role may see (evidence and audit only for
  operator/approver). Never print the token or the password; insert API text into the page as text, not as HTML
  (no `innerHTML` with API data), so log lines cannot inject scripts.

## In scope

- ACR for OD-10 (step 1); serving the web folder (step 2); login + incident list (step 3); incident detail with timeline
  and evidence (step 4); the read-only guard test (step 5); deployment and a demo on vm-095 (step 6).

## Out of scope

Starting investigations, approvals, holds (later: needs a write capability and a safety-principle ACR), live
auto-refresh beyond a "Refresh" button, user management, any change to the API, Slack links.

## Steps

1. **ACR — OD-10.** Copy [`../../architecture/changes/ACR-TEMPLATE.md`](../../architecture/changes/ACR-TEMPLATE.md)
   to `ACR-0001-readonly-ui.md`. Smallest change: OD-10 → "a read-only incident UI over the existing API, served on
   the loopback listener under `/ui`"; §7.1 gets a row `GET /ui/` (static files, loopback only, no auth for the
   files themselves; every data call uses the JWT). Not a safety principle (read-only, no new port), so one
   acceptance is enough. The ACR, the architecture update and step 2 go in the same pull request (protocol §4).
2. **Serve the folder.** Red first in `tests/test_ui.py`: `GET /ui/` returns `index.html`; the API routes still
   work; the files are listed in the package data. Then mount `argus/adapters/inbound/web/` with FastAPI's
   `StaticFiles(html=True)` at the end of `build_api`, and add the package-data entry.
3. **Login + incident list.** The form posts to `/api/v1/auth/token`; the list shows id, target, outcome, class,
   root cause, opened at (newest first, "Refresh" button). Test: the page and its script are served; manual check
   with `uvicorn` on the laptop against the SQLite store.
4. **Incident detail.** Outcome and root cause in a clear box (green = diagnosed / healthy, amber = escalated,
   red = refused), the diagnosis text, the timeline from `/events` (one block per node, the same order as the
   formatted CLI: `argus/adapters/inbound/cli/render.py` shows which fields each node carries), the evidence list.
5. **Read-only guard test.** `tests/test_ui.py` scans `argus/adapters/inbound/web/*.js`: every `fetch` uses `GET` except the token call,
   and only the routes listed in rule 1 appear. Red seen: add a forbidden `POST` on purpose, watch it fail, remove it.
6. **Deploy and show (VM lease).** State probe → `ops/deploy.sh <branch>` on vm-095 → rebuild `argus-v18-agent`
   (it serves the API) → SSH tunnel → open `/ui/` → show the SC-03 incident from the class demo → NO INTERFERENCE.

## Acceptance criteria

1. Full suite green (offline + Postgres in CI); `tests/test_ui.py` covers serving, read-only guard, and that no
   API route changed.
2. On vm-095 through the tunnel: login works for the three users; the list and the detail of a real incident
   (for example the SC-03 one) show outcome, root cause, timeline and evidence; NO INTERFERENCE.
3. ACR accepted and applied (`ARCHITECTURE.md` OD-10 and §7.1 updated, version bumped per the ACR).
4. Brain updated in the last PR: `CURRENT_STATE.md` (what runs), `NEXT_STEP.md`, `tdd/CURRENT_TEST_STATE.md`,
   journal; this file moves to `tasks/completed/`.

## Red seen / evidence

(empty — fill in at each step)
