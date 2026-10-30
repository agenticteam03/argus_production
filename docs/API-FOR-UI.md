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

1. **The public UI logs in with `scope=read` or `scope=investigate`** (ACR-0012). A read token can only read; an investigate token
   reads and may also call `POST /api/v1/investigations` and `POST /api/v1/incidents/{id}/resolve` (ACR-0041),
   nothing else. The team's UI uses `investigate`. Argus
   refuses any other non-`GET` (403, audited as `access.read_only_refused` or `access.investigate_scope_refused`),
   whatever the user's role. A bug in a UI cannot approve or change anything; the most it can do is start an
   investigation (a read of the target), within the quotas.
2. **Show a control only when `GET /api/v1/me` lists its action.** Never decide permissions in the UI. New features
   add actions to `/me`.
3. **Send the token as `Authorization: Bearer <token>`.** Tokens expire after `ARGUS_JWT_TTL_MIN` minutes (30 by
   default); on 401, log in again.
4. **Treat every text field as untrusted text.** Evidence and diagnoses quote container logs; render them as text,
   never as HTML.
5. **Browser access during development** needs `ARGUS_UI_ORIGINS` (comma-separated origins, e.g.
   `http://localhost:5173`) on the agent. Empty by default: no CORS headers at all. In production the UI is served
   by `argus-v18-ui` with a proxy to the API, so no CORS is needed.
6. **In production the UI is behind the public edge** (ACR-0011, `deploy/ui/`). The edge proxies only the routes
   below, each with its method; anything else is 404 there. A login through it **must** ask for `scope=read`
   or `scope=investigate` (otherwise 400; never a full token). Failed logins are limited per username and per
   address: a locked login gets 429 with `Retry-After`.
   The Phase 19 Actions screen is a separate private workflow. Its draft routes are mounted only by an explicit
   composition with action rows and are not reachable through the public edge. A real browser full-token login must
   wait for acceptance and implementation of ACR-0031; the local mock preview cannot answer an approval.
7. **Starting an investigation** (ACR-0012): `POST /api/v1/investigations` with `{"target", "request_kind": "check" |
   "report", "reason"}`, the target taken from `GET /api/v1/targets` (never free text). With an investigate token
   the API applies quotas: 10 an hour and 2 queued per account, 20 queued in all. Over one, 429 with `Retry-After`
   (seconds). Show a "Start" control only when `/me` lists `start_investigation`. A re-check adds `"parent_id":
   "<incident id>"` (ACR-0021): the incident it re-checks, which must exist (else 422, nothing created); quotas are
   the same. Every incident (list row and detail) carries `parent_id` (`null` when it re-checks nothing), and
   `GET /api/v1/incidents?parent_id=<id>` lists that incident's re-checks, newest first.
8. **`limit` is capped by the server** (200 by default, `ARGUS_INCIDENTS_LIMIT_CAP`); asking for more returns at most
   that many.
9. **The runbooks are not an API route:** the edge serves `/runbooks/index.json` and `/runbooks/RB-*.md` only to a
   request whose bearer token passes `GET /api/v1/me` (the frontend's `httpRunbooksAdapter`).
10. **Host metrics** (proposed ACR-0014): `GET /api/v1/host-metrics` reads only the three named host signals already
    in `config/signals.yaml`. No target or PromQL parameter is accepted. Each host returns its sample time and
    independent `null` values when missing; the UI never treats missing data as zero. Each host also carries the lines to draw (`thresholds`, memory as *used*) and its heartbeat age (ACR-0021). Host A = `vm-095`, Host T =
    `vm-166`. The chat answers these bounded metric questions directly. An explicit "Investigate Host T" uses
    the existing investigation route and links to the incident; it does not claim the investigation finished.
11. **Incident metrics** (ACR-0017): `GET /api/v1/incidents/{id}/metrics?range=15m|30m|1h|6h|24h` returns the charts around
    one incident. The browser chooses only the range; the server picks a fixed list of named signals for the
    incident's class (`config/ui-incident-signals.yaml`), reads them on the incident's host only, and returns at most
    ~130 points per series. `null` is a missing sample (draw a gap, never 0); `fired: true` marks the detector's
    signal; `max` and `unit` are optional. ACR-0021 adds, all optional for a client: per series `kind` (`memory`,
    `restarts`, `cpu`, `latency`, `health`, `disk`, `database`, `network`, `other`), `thresholds` (`{warning, critical,
    direction}` scaled like the values, or `null`) and `detector_threshold` (the line at which Argus opens the
    incident, on the `fired` series, else `null`); at the top `incident_from` and `incident_to` (`null` while open),
    `events` (`[{at, kind, label}]`: `restart`, `oom_kill`, `alert_fired`, `alert_resolved`, `deploy`) and a
    template `summary` (never a model call). T-0045 B7 adds `ranges_available` (the ranges this route accepts) and,
    per series, `baseline`: `{p50, p95, from, to}` of the same signal over the 24 h that end an hour before the
    incident opened, scaled like the values, or `null` when under half of that window has samples (draw no band,
    never a guessed one). A `deploy` event's label names the ref and the short commit (`Deployed main (dfa7332)`).
    T-0046 L4 adds `link_broken`, `link_slow` and `link_recovered` events (the recorded link changes of the
    incident's target and its declared dependencies: `Link argus-lab-api → argus-lab-cache broken (timeout)`).
12. **System map** (ACR-0017): `GET /api/v1/topology` returns `hosts` (`role`: `argus` or `monitored`), `nodes` (one
    per inventory target; `target` is the exact text incidents use, so the UI marks the root cause and the affected
    target itself; `status` is `running`, `restarting`, `unhealthy`, `stopped` or `unknown`; `info` is a list of
    label/value facts) and `edges` (`state` `ok`, `broken`, `unknown` or `read`, with the dependency's `port`).
    T-0046 L4: a dependency edge adds `required` (a broken required link is a critical `dependency_broken` problem
    of its owner, unless the owner is idle) and `since` (when its state last changed, or `null` when Argus has not
    recorded it).
    Add `?incident_id=<id>` (operator/approver) for the incident's target and root cause as the incident saw them:
    their real networks, and "no shared network" on their link.
    ACR-0021 adds, all optional for a client: per node `health` (`healthy`, `degraded`, `failed`, `unknown`, `idle`),
    `idle` (a scenario-only lab container that is not running), `networks` (declared; at the incident with the
    overlay), `problems[]` (`{kind, severity, summary, signal, value, threshold, unit}`) and, with the overlay, `role`
    (`root_cause`, `affected`, `on_path`, else `null`); per edge an `id`, a `kind` (`dependency` or `argus_reads`), the
    state of **that** dependency's probe (`ok`, `slow`, `broken`, `unknown`, `read`), `checked_at` (when Argus read the
    probe's value, not when the probe ran), `latency_ms` and
    `reason`; and, with the overlay, `cause_path` (the node ids from the target to the root cause; `[]` without one).
13. **Resolving an escalated incident** (ACR-0041): `POST /api/v1/incidents/{id}/resolve` with `{"reason": "<what
    fixed it, 1-500 characters>"}`, by an operator or approver, with a full or investigate token. Only an `escalated`
    incident, once: anything else is 409 (404 for an unknown id). It becomes `closed`, keeps its `outcome` and
    `diagnosis`, and gains `resolution: {by, at, reason}` (`null` on every other incident); the audit records
    `incident.resolved`. Show a "Resolve" control only on an escalated incident and only when `/me` lists
    `resolve_incident`.
14. **Approvals waiting** (ACR-0042): `GET /api/v1/approvals/waiting` returns only `{"waiting": N}`: how many approvals
    wait for this approver, with the private list's filter (pending, still verifying, in the caller's scope; at most
    50). Any token, no second factor; never an id, an incident, an action or a target. Show it on the bell only when
    `/me` lists `count_waiting_approvals`, and send the person to Actions, where the private login decides them.

## Routes

| Route | Who | Returns | Sample |
|---|---|---|---|
| `POST /api/v1/auth/token` | anyone with a login | a bearer token; form fields `username`, `password`, `scope=read` | [`login.json`](../contracts/samples/login.json) |
| `POST /api/v1/auth/logout` | any token (read and investigate included) | `{"ended": true}`; the token is refused from the next request on (ACR-0018). Call it on logout instead of only dropping the token | — |
| `GET /api/v1/me` | any token | user, role, `access` (`read`/`investigate`/`full`), `actions`, and the role's `permissions` (ACR-0018: show controls by `actions`; `permissions` says what the role could do with a full token) | [`me.json`](../contracts/samples/me.json) |
| `POST /api/v1/ops/auth/token` | anyone, but only on the private path (the edge's client certificate and allowlist; else 404) | ACR-0032: form `username`, `password`; a full `ops` token for a human approver with two security keys, valid only on the private path, until 15 minutes without a request or one hour after the login (401: sign in again); keep it in memory only | — |
| `GET /api/v1/ops/approvals` | private `ops` (or full) human with `approve_action` and a WebAuthn-ready session | the pending approvals in the caller's scope: `id`, `incident_id`, `capability`, `target`, `risk`, `verdict`, `expires_at` | — |
| `GET /api/v1/approvals/waiting` | a human approver, any token, no second factor; only while the action routes are mounted | `{"waiting": N}` (at most 50) (ACR-0042) | — |
| `GET /api/v1/ops/corpus/sources` | private `ops` (or full) human `admin` with a WebAuthn-ready session (`manage_corpus`) | ACR-0034 local tier: the installed and staged reference sources, one row per source: `name` (the source's, or a staged bundle's: a bundle may carry several sources), `source` (the source's own name), `ref`, `licence`, `status` (`installed`/`staged`), `passages`, `quarantined`, `at`, `sha256` | — |
| `POST /api/v1/ops/corpus/sources/{name}/approve` | same | `{step_up_token}`; the step-up is bound to `corpus:<name>:<sha256>` (the staged bundle's passages hash). Verifies the staged hashes and installs the source; 409 if nothing is staged or the bundle changed | — |
| `POST /api/v1/ops/corpus/sources/{name}/reject` | same | `{reason, step_up_token}` (same binding); deletes the staged bundle | — |
| `GET /api/v1/ops/approvals/{approval_id}` | private full-token human with `approve_action` and a WebAuthn-ready session; draft composition only | the frozen proposal, bound judge verdict, state, expiry and `reversible` (the rollback is a catalogue action); the UI opens one known approval ID | — |
| `POST /api/v1/ops/approvals/{approval_id}/answer` | same private caller plus a fresh object-bound WebAuthn step-up | `decision` (`approved`/`denied`), exact `proposal_digest`, `step_up_token`, `confirmation_target` (the host-qualified target, for red-risk approval) and `reason` (required for `denied`); writes a chained audit row with the answer; returns the recorded state | — |
| `GET /api/v1/incidents?limit=30` | any role | the latest incidents, newest first | [`incidents.json`](../contracts/samples/incidents.json) |
| `GET /api/v1/incidents/{id}` | any role; `evidence` and `audit` only for operator/approver | one incident with its diagnosis and, derived from the stored record (never a model call), the verdict card's fields (ACR-0021): `severity` (`critical`, `warning`, `ok`, or `null` while unknown), `summary`, `cause` (`{target, kind, statement, confidence 0.9 / 0.6 / 0.3, confidence_label}` or `null`), `evidence_highlights[]` (up to 3 cited, `{evidence_id, text, stance}`; empty for a viewer), `not_checked[]`, `cause_path[]`, `duration_ms` (`null` while open), `next_actions[]` (`[]` for now), `hypotheses[]`: the explanations the model weighed at its final step, best first (ACR-0024, T-0047 H3): `{id, statement, cause_class, target, relation, status, rank, chosen, support: {score, for, against}}` (`for` / `against`: the cited evidence records; `target` `null` for an external cause), plus the cited `support_ids[]` and `against_ids[]` for operator/approver only; `[]` when the run stated none; and `ranking_disagrees` (`true` when the chosen explanation is not ranked first: the UI can say "the evidence favours <first>") | [`incident.json`](../contracts/samples/incident.json) |
| `GET /api/v1/incidents/{id}/events?after=0` | any role | the run's timeline, one event per node phase; poll with `after=<last seq>` | [`events.json`](../contracts/samples/events.json) |
| `GET /api/v1/evidence/{id}` | operator, approver | one evidence record with its SHA-256 | [`evidence.json`](../contracts/samples/evidence.json) |
| `GET /api/v1/escalations` | any role | the escalations Argus raised to humans | [`escalations.json`](../contracts/samples/escalations.json) |
| `GET /api/v1/targets` | any role | the inventory's targets: `target`, `host`, `kind`, `name` (ACR-0012) | [`targets.json`](../contracts/samples/targets.json) |
| `GET /api/v1/host-metrics` | any authenticated role | current CPU, memory and root-disk ratios for the inventory's host targets, plus `observed_at` and `available` (proposed ACR-0014); per host the gauges' `thresholds` (`cpu_busy_ratio`, `memory_used_ratio`, `disk_used_ratio`, each `{warning, critical, direction}`) and the monitoring heartbeat's `heartbeat_age_s` and `heartbeat_stale` (both `null` when no heartbeat is recorded; stale = older than 150 s) (ACR-0021, T-0045 B1) | [`host-metrics.json`](../contracts/samples/host-metrics.json) |
| `GET /api/v1/incidents/{id}/metrics?range=30m` | any authenticated role | `incident_id`, `range`, `from`, `to`, `step_s`, `ranges_available`, `series[]` of `{key, title, unit, max, fired, kind, thresholds, detector_threshold, baseline, points: [[time, value or null]]}`, `incident_from`, `incident_to`, `events[]`, `summary` (ACR-0017, ACR-0021) | [`incident-metrics.json`](../contracts/samples/incident-metrics.json) |
| `GET /api/v1/topology[?incident_id=<id>]` | any authenticated role; the `incident_id` overlay for operator/approver | `observed_at`, `hosts[]`, `nodes[]`, `edges[]` (nodes add `health`, `idle`, `networks`, `problems`, `role`; edges add `id`, `kind`, `checked_at`, `latency_ms`, `reason`; ACR-0021; and `required`, `since`; T-0046 L4) (and `incident_id` with the overlay) (ACR-0017) | [`topology.json`](../contracts/samples/topology.json), [`topology-incident.json`](../contracts/samples/topology-incident.json) |
| `POST /api/v1/investigations` | operator, approver; full or **investigate** token | `incident_id`, `status`, `duplicate` (202); quotas for an investigate token (ACR-0012) | [`investigation.json`](../contracts/samples/investigation.json) |
| `POST /api/v1/incidents/{id}/resolve` | operator, approver; full or **investigate** token | the closed incident with its `resolution` (200); 409 unless escalated (ACR-0041) | [`incident-resolved.json`](../contracts/samples/incident-resolved.json) |
| `GET /api/v1/target-metrics?target=<host/kind:name>&range=15m` | any authenticated role | one inventory target's recent signals (ACR-0021): `target`, `range` (`15m` or `1h`), `from`, `to`, `step_s`, `series[]` of `{key, kind, title, unit, max, thresholds, points: [[time, value or null]]}`; a container gives CPU quota used and memory, a host CPU, memory used and disk used; `404` for a target not in `/api/v1/targets`, `422` for a bad range; shared for 30 s | [`target-metrics.json`](../contracts/samples/target-metrics.json) |
| `GET /api/v1/overview` | any authenticated role | the dashboard in one answer (ACR-0021): `observed_at`, `status` (the worst open severity: `critical`, `warning`, `info`, or `ok` when nothing is open), `open_incidents` (`{critical, warning, info}`), `latest_open[]` (the 5 newest open: `{id, target, host, severity, kind, summary, opened_at, next_action}`; `info` = no class yet; `next_action` `null` for now), `hosts[]` (the `/host-metrics` rows), `fleet` (boxes by `health`: `{healthy, degraded, failed, unknown, idle}`), `links` (`{ok, total}` of the declared dependencies), `last_closed_at`; built from the store and the topology and host-metrics snapshots, no new host read; shared for 15 s | [`overview.json`](../contracts/samples/overview.json) |
| `GET /api/v1/ops/console/incidents/{id}/commands` | a human with `investigate`, private path only | ACR-0043: the operator console's allowed commands `{commands: [{id, usage, class, scenario, summary}]}`; mounted with `ARGUS_OPERATOR_CONSOLE=1` (else, and off the private path, `404`) | — |
| `POST /api/v1/ops/console/incidents/{id}/execute` | same | body `{input}` (at most 200 characters), optional `suggestion_id` (at most 64, the suggestion the operator inserted unedited, CON-5) and `confirmation` (CON-6); `{command_id, input, command, class, status, output[], started_at, finished_at}`, `status` `ok`, `error` or `rejected` (refused before anything ran, the reason as the only line, `command` and `class` null for a parser refusal); stored and audited (a budget refusal is only audited); `429` with `Retry-After` over a person's limit (20 reads a minute, 200 an hour; `help`, `clear`, `history` not counted), `rejected` once the incident's own read budget is used; write commands do not run until CON-6 | — |
| `POST /api/v1/ops/console/incidents/{id}/sessions` | same | T-0016: the person opens the console on this incident; body `{reason}` (3 to 300 characters, required); `{session_id, opened_at, limit_min, expires_at}` (`limit_min` 30, the panel's countdown). Audited as `console.session_opened` with the person and the reason (the incident's Audit tab). A record, not a gate: `execute` does not need it | — |
| `POST /api/v1/ops/console/incidents/{id}/sessions/{session_id}/close` | same | body `{why}`: `disconnect`, `time_limit` or `signed_out`; `{closed: true}`, audited as `console.session_closed`. A refused console request of a signed-in principal (a viewer, a service or agent, a narrowed token) is audited as `security.console_refused`, which alerts the team (Telegram) | — |
| `GET /api/v1/ops/console/incidents/{id}/history` | same | `{entries: [{command_id, input, command, class, status, output[], by, started_at, finished_at}]}`: the incident's stored commands, refusals included, oldest first, `output` as lines like `execute` (cut at 4 KB); each command Argus analysed has `analysis` (CON-4b): `status` `waiting` (with `countdown_s` and `settle_until`), `analyzing`, `done` (`comment` of two or three sentences that cite the output or a metric, `evidence` `[{hypothesis_id, effect, reason, reference, evidence_id}]`, `ranking` `[{id, rank, score, counted_for, counted_against}]` recomputed by the deterministic ranking, optional `suggestion` `{id, command, command_id}`) or `error` (`message`, `reason`, never a comment); `retryable` says whether a re-check may be asked; meta commands and refusals have none | — |
| `POST /api/v1/ops/console/incidents/{id}/commands/{command_id}/recheck` | same | CON-4b: look again at a command's result when its analysis is `retryable` (metrics were not available, the analysis failed or ran long): `202` `{command_id, analysis}` at once, the result comes with the history; `409` when it is not retryable, `404` for an unknown incident or command, `429` when the person is already at the read limit (a re-check is refused there but adds no read, so it does not use any of the limit); audited as `console.recheck` | — |
| `POST /api/v1/auth/webauthn/register/options` | any token | body `{ticket}` for the first key (the code another administrator gave), or `{step_up_token}` (a step-up for `webauthn.register:<user>`) for a further one; `{challenge_id, options}`: pass `options` to `navigator.credentials.create` (ACR-0018 step 3) | — |
| `POST /api/v1/auth/webauthn/register/verify` | any token | body `{challenge_id, credential, label}` (`credential` = the PublicKeyCredential as JSON); `{credential, enrolled}` | — |
| `POST /api/v1/auth/webauthn/login/options`, `…/login/verify` | any token | completes this login with a key (`navigator.credentials.get`); `{verified: true}`; `/me`'s `second_factor.verified` turns true | — |
| `POST /api/v1/auth/webauthn/step-up/options`, `…/step-up/verify` | any token | body `{object}` (`kind:reference`) for the options; the verify answers `{step_up_token, expires_at}`: single-use, 5 minutes, for that object only; the privileged route takes it | — |
| `GET /api/v1/auth/webauthn/credentials` | any token | the caller's keys: `{credential, label, created_at, last_used_at}` | — |

Errors: `401` no token, invalid or expired token; `403` the role or a read-only token may not do this; `404` unknown
incident or evidence id; `400` a login asked for a scope other than `read`.

## Actions listed by `/me`

| Action | Given to | The UI may show |
|---|---|---|
| `view_incidents` | every role | the incident list and each incident's summary |
| `view_timeline` | every role | the run events (detect → recall → investigate ⇄ act → record) |
| `view_evidence` | operator, approver | evidence records and the audit trail |
| `start_investigation` | operator, approver, with a full or an **investigate** token | the "Start an investigation" form and "Investigate again" (ACR-0012) |
| `count_waiting_approvals` | approver, any token, while the action routes are mounted | the bell's count of approvals waiting (ACR-0042) |
| `manage_second_factor` | every role, when the second factor is configured | enrolling a key and completing the login with it; `/me`'s `second_factor` is `{enrolled, verified}` (`null` when not configured) (ACR-0018 step 3) |

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
 "opened_at": "2026-10-06T15:45:55.575099+00:00", "root_cause_target": "vm-166/container:argus-lab-worker",
 "parent_id": null}
```

One timeline event (`GET /api/v1/incidents/{id}/events`):

```json
{"seq": 1, "incident_id": "inc_7e49840f50fa", "node": "detect", "phase": "enter", "at": "2026-10-06T15:45:55.622566+00:00",
 "data": {"host": "vm-166", "target": "vm-166/container:argus-lab-worker", "request": "report", "trigger": "manual",
          "scope": ["vm-166/container:argus-lab-worker", "vm-166/host:vm-166"]}}
```

The full bodies, including the incident detail with its evidence and audit trail, are in
[`../contracts/samples/`](../contracts/samples/).
