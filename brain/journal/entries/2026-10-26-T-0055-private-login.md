## 2026-10-26 - T-0055: phase 19 continued, ACR-0032 applied: the private login, the ops token, the pending list

Type: implementation
Who: conantkd (+ agent)
Context: built as a draft stacked on #324 while ACR-0032 (#325) was proposed. juanbetancurm accepted ACR-0032 on
#325 (2026-10-27, with the second approval for least privilege and secrets) and both #324 and #325 merged; the
branch now targets `main` (main merged in) and records the acceptance.
Decision / result:
- `POST /api/v1/ops/auth/token` (mounted only with the action routes): 404 unless the edge says private path
  (`X-Argus-Ops: 1`); a full `ops` token only for a human approver with two WebAuthn credentials; the limiter,
  lockout and audit of the public login (`via: ops`); it ends after 15 minutes without a request or one hour after
  the login (changed from 30 minutes absolute by `conantkd` on 2026-10-26; `auth_session.last_seen_at` in
  migration 017, refreshed by each request on the private path in one UPDATE; refused as `security.session_refused`
  with reason `idle`).
- An `ops` token is refused on any request without `X-Argus-Ops: 1` (the WebAuthn ceremonies included), audited as
  `security.session_refused` with reason `off private path` (one of the alerting events of #344).
- The edge sets `X-Argus-Ops $argus_ops_ok` on every proxied request, replacing a browser's copy.
- Migration 017 widens `auth_session`'s access CHECK with `ops`; `argus db check` gains the insert and the refusal.
- `GET /api/v1/ops/approvals`: the pending approvals in the caller's scope (one that no longer verifies is left out).
- The private-path test now checks the mounted action routes, with the private login as the one exception.
- `/me` lists `approve_action` and `place_hold` among the actions once granted (the UI shows only what `/me` lists;
  before, the Actions entry could never appear outside the local demo).
- UI: Actions is an approver's entry and leads through three steps: the private sign-in (the `ops` token replaces
  the public one in memory, the public session is ended on the server and its stored copy forgotten), the security
  key that confirms the session, then the pending list and the frozen proposal. The UI contract adds the two routes.
- `ARCHITECTURE.md` 1.8.38 (§14.3, §17.3 and the changelog); ACR-0032 `accepted`, §6 ticked but the deployment.
- After the merges, from the reviews of #325 and #324:
  - the API believes `X-Argus-Ops` only from the edge itself (`ARGUS_OPS_PEER`, default `argus-v18-ui`, resolved at
    each request): the worker, the tunnel and the egress proxy share `argus-v18-core` with the API and could send
    the header without the edge (#325 note 1);
  - a refused private login is `access.ops_login_failed`, an alerting event (ACR-0032 §4); the public
    `access.login_failed` still does not page;
  - the edge test on the real nginx image covers the login route itself (no certificate, revoked, foreign, an
    address not allowed: 404) and the loopback server (#325 note 2);
  - from conantkd's review of `daab22a`: the runbooks' auth subrequest (`/_argus_auth`) sets `X-Argus-Ops` to the
    edge's `$argus_ops_ok` (it forwarded the browser's copy, so a forged header made an `ops` token pass there and
    a real private request failed); the pending approvals list pages through the store (keyset on
    `requested_at, approval_id`) and filters before it fills its 50, so older rows out of scope no longer hide one
    in scope;
  - `GET /api/v1/ops/holds?target=<host>/<name>` lists the host's holds too, as the approval check refuses on them
    (#324 note 2; SQLite and Postgres).
- `argus/actions/gateway_client.py`: the worker's client of the action gateway (the catalogue's exact route, the
  frozen target and identity, the action ID, the token from a worker-only file, never shown); a refusal is `failed`,
  a duplicate or an ambiguous answer is left to `status`. Tested against the gateway listener and the real image.
  The worker's token mount stays out of compose: the standing write-gate check refuses it while the gate is closed;
  phase 20's release PR adds it.
- Leases as holds (ACR-0019 §3.11), decided by `conantkd`: by process, not code. An approver answers `approved` only
  while holding the target VM's lease (`policies/PARALLEL_LANES.md` §1); Argus does not read the leases; holds and
  the emergency stop still stop everyone. ACR-0019 §3.11 records the reading.
Consequences: deploy order when it ships: backup, migration 017, then the image, then `argus db check`; the edge's
`proxy.conf` change needs the UI image rebuilt. ACR-0032 §6's last box (deployment evidence) waits for that deploy.
References: [PHASE-19 task](../../tasks/current/PHASE-19-approval-ui-gateway.md), #324, #325.

### Test state

Red first for each piece: the private login 4, the edge's header 3 (real nginx image), the `ops` session on Postgres
(`auth_session_access_check`), the pending list 2, `/me`'s actions 1; UI 6. After the merges, red first: the header
from a neighbour that is not the edge, `access.ops_login_failed` alerting, the host hold listed, the idle end (+10 and
+24 minutes alive, +40 ended) and the store refreshing only a live session. After the review of `daab22a`, red first: the forged and the real private runbook request on the real nginx
image, the in-scope approval behind 55 hidden ones (SQLite), and the keyset page on Postgres. Before that: full suite
2232 passed, 41 skipped
(Postgres in CI); the edge tests on the real nginx image 59 passed; frontend 195 passed; the migration checker passes
on 017.

### Next step

Review of #347 (protected paths: a teammate's approval). #324's note 4 (an approver releasing a host-wide hold) is
answered by process: `PARALLEL_LANES.md` §1, release a host's hold only with that VM's lease or when you placed it.
After merge: the deploy (backup, migration 017, the agent image,
`argus db check`, the UI image), then phase 20.
