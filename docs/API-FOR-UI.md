# The Argus API for user interfaces

A user interface (UI), for example the team's web frontend, is a **separate client of the HTTP API**, like the
console (ACR-0001, `brain/architecture/ARCHITECTURE.md` §7.1, §17.3). This page lists the only routes a UI may rely
on. Anything else can change without notice.

- **Machine-readable contract:** [`../contracts/ui-api.json`](../contracts/ui-api.json): the OpenAPI schema of exactly
  these routes. Paths, parameters, authentication and the login form are guarded there. Most read routes have no
  declared response model, so the response bodies are guarded by the samples.
- **Sample responses:** [`../contracts/samples/`](../contracts/samples/): real responses from a scripted run with
  one SC-03-like diagnosis (vm-166 worker OOM-killed) and one unsupported report (vm-095, escalated). A UI's tests
  can use them as a fake API.
- **The guard:** `tests/test_ui_contract.py` compares the running API with both. A change that would break a UI
  turns CI red for whoever made it. To change the contract on purpose, regenerate it and let the pull request's
  reviewer see the diff:

  ```bash
  ARGUS_UPDATE_UI_CONTRACT=1 python -m pytest tests/test_ui_contract.py
  ```

## Rules for every UI

1. **Log in with `scope=read`.** The token can then only read. Argus refuses it on every route that is not a `GET`
   (403, audited as `access.read_only_refused`), whatever the user's role. A bug in a UI cannot start, approve or
   change anything.
2. **Show a control only when `GET /api/v1/me` lists its action.** Never decide permissions in the UI. New features
   add actions to `/me`.
3. **Send the token as `Authorization: Bearer <token>`.** Tokens expire after `ARGUS_JWT_TTL_MIN` minutes (30 by
   default); on 401, log in again.
4. **Treat every text field as untrusted text.** Evidence and diagnoses quote container logs; render them as text,
   never as HTML.
5. **Browser access during development** needs `ARGUS_UI_ORIGINS` (comma-separated origins, e.g.
   `http://localhost:5173`) on the agent. Empty by default: no CORS headers at all. In production the UI is served
   by `argus-v18-ui` with a proxy to the API, so no CORS is needed.

## Routes

| Route | Who | Returns | Sample |
|---|---|---|---|
| `POST /api/v1/auth/token` | anyone with a login | a bearer token; form fields `username`, `password`, `scope=read` | [`login.json`](../contracts/samples/login.json) |
| `GET /api/v1/me` | any token | user, role, `access` (`read`/`full`), `actions` | [`me.json`](../contracts/samples/me.json) |
| `GET /api/v1/incidents?limit=30` | any role | the latest incidents, newest first | [`incidents.json`](../contracts/samples/incidents.json) |
| `GET /api/v1/incidents/{id}` | any role; `evidence` and `audit` only for operator/approver | one incident with its diagnosis | [`incident.json`](../contracts/samples/incident.json) |
| `GET /api/v1/incidents/{id}/events?after=0` | any role | the run's timeline, one event per node phase; poll with `after=<last seq>` | [`events.json`](../contracts/samples/events.json) |
| `GET /api/v1/evidence/{id}` | operator, approver | one evidence record with its SHA-256 | [`evidence.json`](../contracts/samples/evidence.json) |
| `GET /api/v1/escalations` | any role | the escalations Argus raised to humans | [`escalations.json`](../contracts/samples/escalations.json) |

Errors: `401` no token, invalid or expired token; `403` the role or a read-only token may not do this; `404` unknown
incident or evidence id; `400` a login asked for a scope other than `read`.

## Actions listed by `/me`

| Action | Given to | The UI may show |
|---|---|---|
| `view_incidents` | every role | the incident list and each incident's summary |
| `view_timeline` | every role | the run events (detect → recall → investigate ⇄ act → record) |
| `view_evidence` | operator, approver | evidence records and the audit trail |
| `start_investigation` | operator, approver, **full token only** | nothing in a read-only UI: a read token never gets it |

## Examples

Log in (form-encoded, like OAuth2):

```bash
# vm-095's loopback port, reached through ssh -L
curl -s -X POST http://127.0.0.1:18000/api/v1/auth/token \
  -d username=alice -d password=... -d scope=read
```

```json
{"access": "read", "access_token": "<a JWT>", "token_type": "bearer"}
```

Who am I:

```json
{"user": "alice", "role": "operator", "access": "read",
 "actions": ["view_incidents", "view_timeline", "view_evidence"]}
```

One row of `GET /api/v1/incidents`:

```json
{"id": "inc_7e49840f50fa", "target": "vm-166/container:argus-lab-worker", "status": "closed",
 "outcome": "diagnosed", "class": "container_restart_loop", "strategy": "model_loop",
 "opened_at": "2026-10-06T15:45:55.575099+00:00", "root_cause_target": "vm-166/container:argus-lab-worker"}
```

One timeline event (`GET /api/v1/incidents/{id}/events`):

```json
{"seq": 1, "incident_id": "inc_7e49840f50fa", "node": "detect", "phase": "enter", "at": "2026-10-06T15:45:55.622566+00:00",
 "data": {"host": "vm-166", "target": "vm-166/container:argus-lab-worker", "request": "report", "trigger": "manual",
          "scope": ["vm-166/container:argus-lab-worker", "vm-166/host:vm-166"]}}
```

The full bodies, including the incident detail with its evidence and audit trail, are in
[`../contracts/samples/`](../contracts/samples/).
