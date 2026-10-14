# ACR-0012 — The UI may start an investigation (an "investigate" token, through the public edge)

An Architecture Change Record is the **only** way to change `brain/architecture/ARCHITECTURE.md`. ACRs are never
fast-tracked. This one widens what a token reached from the Internet may do (least privilege), so it needs **a
second approval** in its pull request.

| Field | Value |
|---|---|
| Status | `proposed` — implemented on the local branch `task/ACR-0012-impl` (2026-10-14, not pushed, no PR yet): ARCHITECTURE 1.8.11 applied there; accepted only with a teammate's approval and the second approval of its implementation PR |
| Proposed by | conantkd (+ agent) · 2026-10-14 |
| Accepted by | — |
| Second approval (safety principle only) | required: least privilege (a public token that can start work on the hosts) |
| Architecture version | from `1.8.10` → `1.8.11` (1.8.9 is reserved by ACR-0010), or the next free number when applied |
| Task / PR | T-0016 "Level 1 Investigate" (`tasks/current/T-0016-frontend.md`, "Later: from reading to acting") · PR #… |

**How to read the facts below.** **(O)** observed (code or VM) on 2026-10-14, **(D)** documented, **(S)** assumed.
Nothing here is implemented.

## 1. Detect and explain

The UI is public since 2026-10-14 (ACR-0011, T-0016 4e), and **read-only**. To ask Argus "diagnose this container"
an operator still needs the CLI or Swagger, so SSH. The team wants the button in the UI.

| Fact | Kind | Source |
|---|---|---|
| `POST /api/v1/investigations` exists: `target`, `reason` (≤ 2000 chars), `request_kind` `check`/`report`, optional `idempotency_key`; roles `operator`, `approver`; it queues an incident (202) | O | `adapters/inbound/http.py` |
| A read token is refused on every non-`GET` (403, audited `access.read_only_refused`); `/me` lists `start_investigation` only for a **full** token | O, D | §17.3 (ACR-0001); `http.py` |
| The edge's logins are read-only (400 otherwise), and `POST /api/v1/investigations` is not proxied (404) | O | ACR-0011; T-0016 4e evidence |
| **No limit on starting investigations**: not per user, not per minute, no cap on queued incidents | O | `http.py`; no quota in `argus/` |
| One worker runs one incident at a time; an incident is bounded by `ARGUS_MAX_STEPS` (8) and the per-capability `max_per_incident` | O, D | `wiring.py`; `config/policy.yaml`; §10.2 |
| Cost of one investigation, `main`, 55 cases × 5: about 3.5 model calls, 3.8 reads, p50 8 s; the classes `dependency_unavailable` and `nginx_upstream_failure` run the baseline (no model call, D-003 #145) | O | EVAL-main; D-003 |
| A target outside the inventory is refused before any read and audited (SC-11, 5/5) | O | E2E-8 |
| Reads only: the write gate is empty; no write capability exists in this release | D, O | §13.3; `WRITE GATE CLOSED` on vm-095 |
| The UI's accounts are the three **shared** `operator` accounts (an accepted risk of ACR-0011) | O, D | `principal` table; ACR-0011 §10 |
| The frontend already has the place: the agent chat is a placeholder ("needs a new ACR"); a control is shown only when `/me` lists its action (ACR-0001 rule 2) | O | `httpArgusAdapter.askAgent`; `GUIDELINES.md` |

## 2. Why the current architecture is insufficient

- **§17.3 / ACR-0001:** "in this release a UI holds only read-only tokens; a UI write action needs a new ACR".
  Starting an investigation is not a write to a host, but it is a **POST** that makes Argus read the hosts and call
  the model, so a read token cannot do it. The only token that can is a **full** token, which also allows every
  other non-`GET` route and future write actions: too wide for a public browser.
- **ACR-0011 §3.1 row 6:** a login through the edge issues only read tokens, and the edge proxies only GETs plus
  the login.
- **Nothing limits how many investigations a principal starts.** Behind SSH that was acceptable. Behind a public
  page, with shared accounts, one stolen password could queue hundreds: model cost, reads on the target hosts, and a
  worker queue that delays the alerts' own investigations.

## 3. Smallest reasonable change

### 3.1 The design

| # | Topic | Proposal |
|---|---|---|
| 1 | A third kind of token | A login may ask `scope=investigate`. The JWT carries `access: "investigate"`, which allows every `GET` **and exactly one** non-`GET`: `POST /api/v1/investigations`. Any other non-`GET` → 403, audited `access.investigate_scope_refused`. Like `read`, it only **narrows** the role (`viewer` cannot start investigations whatever the token). `full` stays loopback-only. |
| 2 | The edge | A login through the edge may ask `scope=read` or `scope=investigate`, never full (400). The edge proxies `POST /api/v1/investigations` (one more allowlist line), with its own `limit_req` zone (about 6 per minute per address, burst 2) and `client_max_body_size 4k`. |
| 3 | `/me` | `start_investigation` is listed for an `investigate` token of an `operator`/`approver`. The UI shows the button only then. |
| 4 | Quotas (server) | Per principal: **at most 10 investigations an hour and 2 queued at once**; globally: **at most 20 queued** (manual ones; alerts and schedules are not counted or blocked). Over a quota: 429 with `Retry-After`, audited `investigation.quota_refused`. Settings in §20.1. A repeated `idempotency_key` keeps returning the same incident (unchanged). |
| 5 | What a UI may ask | `target` from a list the UI builds from the inventory, never free text (`GET /api/v1/targets`, new read route: the inventory's target refs and kinds, no addresses); `request_kind` `check` or `report`; `reason` free text (≤ 500 chars from the UI; shown as text). The API keeps its own checks: unknown target refused and audited (SC-11). |
| 6 | Audit and attribution | The incident's `principal` is the login (as today), plus `detail.via: edge` on `incident.started`. **With shared accounts, an investigation cannot be attributed to a person:** stated as a risk (§4). |
| 7 | Frontend | A "Diagnose" button on an incident's target and in a small form on the dashboard (target from the list, check/report, reason); after the 202 it opens the new incident, whose timeline the UI already follows. The agent chat stays a placeholder (a free-text question is not an investigation). |
| 8 | Contract | `contracts/ui-api.json` gains `POST /api/v1/investigations` and `GET /api/v1/targets`, with samples; the contract test, the edge's allowlist test and the Playwright guard follow (the guard allows that one POST only when `/me` lists the action). |

### 3.2 `ARCHITECTURE.md`, before → after (the minimal text)

- **§17.3, read-only tokens** — after: "… The login may also ask for `scope=investigate`: `access: "investigate"`
  allows every `GET` and `POST /api/v1/investigations` only (ACR-0012); any other non-`GET` is refused (403,
  audited)."
- **§7.1** — add `GET /api/v1/targets` (the inventory's target refs and kinds, any role); the investigation route's
  quotas (§3.1 row 4); the public edge also proxies `POST /api/v1/investigations`.
- **§20.1** — `ARGUS_INVESTIGATIONS_PER_HOUR` (10), `ARGUS_INVESTIGATIONS_QUEUED_PER_PRINCIPAL` (2),
  `ARGUS_INVESTIGATIONS_QUEUED_MAX` (20).
- **§25 OD-10** — "in this release a UI holds only read-only tokens" → "… read-only tokens, or `investigate`
  tokens that may start an investigation (ACR-0012); any UI write action still needs a new ACR".
- **§17.1 layer 14 (public edge)** — "+ one POST, with its own rate limit".
- **Changelog** `1.8.11`.

**Alternatives considered:**
- **A — Give the UI full tokens through the edge.** Rejected: a full token allows every non-`GET`, today and as
  later write actions arrive; a browser on the Internet should hold the narrowest token that does the job.
- **B — No new token; let `read` tokens POST to investigations.** Rejected: it breaks the meaning of `read`
  (ACR-0001's guarantee "a read token cannot start anything"), which the guard and the tests rely on.
- **C — Keep investigations in the CLI/Swagger only.** The current state; it keeps the SSH requirement for the one
  action operators use most.
- **D — Quotas only at the edge (Nginx).** Not enough: Nginx counts per address, not per principal, and does not
  know the queue; the API must refuse.

## 4. Consequences

- **Code:**
  - `adapters/inbound/http` (the `investigate` access, `/me`, `GET /api/v1/targets`, quotas);
  - `deploy/ui/nginx/locations.conf` (one location);
  - `frontend/` (button, form, adapter);
  - `contracts/`;
  - tests: unit, contract, edge, Playwright.
  - The domain, use cases, policy, tools and the write gate are **not touched**.
- **Deployment:** the agent and `argus-v18-ui` on vm-095.
- **Risk:**
  - **Cost and load** from the Internet. Bounded by the quotas (10/h and 2 queued per principal, 20 queued in
    all), the per-address edge limit and `max_steps`. Alerts are never blocked.
  - **Shared accounts.** Anyone with the shared password can start investigations, and they cannot be told apart.
    Recommended before enabling: one account per person, at least for those who will use the button.
  - **Misuse of `reason`.** It is free text that reaches the model's context. It is redacted and treated as data
    (§10.8), as for a CLI report today.
- **How to reverse it:**
  - stop issuing `investigate` tokens (a setting);
  - remove the edge location;
  - the UI hides the button because `/me` stops listing the action.
  - Existing tokens expire within 30 min.
- **Safety principle touched?**
  - **Least privilege: yes.** A token reachable from the Internet can make Argus read hosts and call the model.
  - **Read-only, the write gate, host isolation, evidence integrity, secrets: no.** Investigations only read; the
    write gate stays empty.
  - **A second approval is required.**

## 5. Decision

Proposed by `conantkd` on 2026-10-14. Waiting for a teammate's acceptance and a second approval. Before enabling it
on the public UI, the team decides on per-person accounts (row 6 and §4).

## 6. Documents to update after acceptance

| Where | What |
|---|---|
| `ARCHITECTURE.md` | §7.1, §17.1 (layer 14), §17.3, §20.1, §25 OD-10, changelog |
| `docs/API-FOR-UI.md`, `contracts/ui-api.json`, `contracts/samples/` | the investigate scope, `POST /api/v1/investigations`, `GET /api/v1/targets`, the quotas |
| `frontend/GUIDELINES.md`, `README.md` | the Diagnose button and form; the guard's one allowed POST |
| `brain/tasks/current/T-0016-frontend.md` | "Level 1 Investigate" as its steps (API, edge, frontend, VM) |
| `brain/policies/SECURITY.md` | least privilege: the public edge may start investigations with an `investigate` token, under quotas |

## 7. Implemented (`task/ACR-0012-impl`, 2026-10-14; not deployed, no PR yet)

- **API** (`adapters/inbound/http.py`):
  - `scope=investigate` → `access: "investigate"`; the edge issues `read` or `investigate`, never a full token;
  - any other non-`GET` → 403, audited `access.investigate_scope_refused`;
  - `/me` lists `start_investigation` for a full or investigate token of an operator or approver;
  - quotas: `per_hour` 10, `queued_per_principal` 2, `queued_max` 20; 429 with `Retry-After`, audited
    `investigation.quota_refused`;
  - every accepted request is audited `investigation.requested` (access, via, client, target);
  - `GET /api/v1/targets` lists refs, host, kind and name.
  - Tests: `tests/test_acr0012_investigate.py`, 16 (12 red seen).
- **Contract:** `contracts/ui-api.json` gains the two routes; the samples `targets.json` and `investigation.json`
  are new, and the existing samples are unchanged.
- **Edge:** `location = /api/v1/investigations` (POST, its own zone at 6 per minute per address with burst 2, 4 KB
  body) and `= /api/v1/targets`. `tests/test_acr0011_ui_edge.py`: 29, with a burst giving 429 and an oversized body
  giving 413.
- **Frontend:**
  - the login asks `scope=investigate`;
  - `DiagnoseForm`: on the dashboard, a target from the list, check/report and a reason of up to 500 characters;
    on an incident page, "Investigate again". It is shown only when `/me` lists the action, and a 429 shows when
    to retry;
  - the Playwright guard allows that one POST only for a session that may start one.
  - Tests: unit 85, acceptance 14 (stable in four runs).

**One difference from §3.1 row 4.** The quotas count and limit **investigate tokens only**. A full token, which is
loopback only (the CLI and the E2E runner), is not limited: the runner starts many investigations a batch by design,
and it never reaches the Internet. Alerts and schedules are never counted, as written.
