# T-0016 step 4d — evidence: the UI edge on vm-095's loopback, against the real API (2026-10-14, conantkd)

Both leases (session fb04b6238725). Run by conantkd's agent over ssh. ACR-0011 is `proposed`, built in PR #144
(one approval of two), so this step deploys a **task branch** and **no public port**. Commands: [`code.bash`](code.bash).

## Deployment

| Block | Expected | Observed | Result |
|---|---|---|---|
| A.1 vm-095 → `task/T-0016-playwright` + agent | SESSION OK; BACKUP OK; DEPLOY OK; one image, restarts 0, health 200, 20/20, 55/55, WRITE GATE CLOSED; NO INTERFERENCE | `SESSION OK`; `BACKUP OK` (2142195 bytes); `DEPLOY OK: d5d992c11cb7 (task/T-0016-playwright)`; agent, worker, scheduler recreated together on image `8c9ac651a048`, `running restarts=0`; `health 200`; `worker: no startup errors`; `20/20`; `55/55`; `WRITE GATE CLOSED`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| U.1 vm-095 `argus-v18-ui` loopback | healthy, uid 101, read-only, only `127.0.0.1:18010`; NO INTERFERENCE | built and started in 44 s; `running health=healthy restarts=0 user=101 ro=true`; ports `8080/tcp -> 127.0.0.1:18010` only; no listener on 443/80; image 78.1 MB; `NO INTERFERENCE` (the edge's published port left out by `nonint-check`) | OK |
| vm-166 | unchanged (no target service changed) | `commit=ad72617…` `ref=main`; `NO INTERFERENCE` | OK |

## U.2 — the edge in front of the real API, through `ssh -L` (no password used)

| Request | Expected | Observed |
|---|---|---|
| `GET /`, `GET /incidents/inc_x` | 200 (the app; SPA route) | 200, 200 |
| `GET /docs`, `GET /openapi.json` | 404 (Swagger stays on loopback) | 404, 404 |
| `GET /api/v1/me`, `GET /api/v1/incidents` without a token | 401 (the real API) | 401, 401 |
| `POST /api/v1/investigations` | 404 (not in the contract) | 404 |
| `GET /api/v1/auth/token` | 403 (wrong method) | 403 |
| `GET /api/v1/approvals` | 404 | 404 |
| `GET /runbooks/index.json` without a token / with a bad one | 401 (`auth_request` to the real `/api/v1/me`) | 401, 401 |
| headers of `/` | CSP, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, no version | all present; `Server: nginx` (no version) |
| the served bundle | no demo password, no runbook text, loads `/runbooks/index.json` | `argus-demo` 0, runbook text 0, reference 1 |
| 6 failed logins of a made-up user (`edge-probe-…`) within a second | 401 × 5, then 429 | `401 401 401 401 401 429`: the 6th stopped by **Nginx's** login `limit_req` (it never reached the API) |
| a 7th, 15 s later | 429 from the **API** lockout, `Retry-After` | `429`, `Retry-After: 854` |
| audit rows of that user (Postgres, read-only) | `access.login_failed` × 5 and `access.login_locked` × 1, all `via: edge` | exactly those; `client` = `172.30.0.1` |

**Reading:**
- **Both layers work.** Nginx cuts a burst at the 6th login a minute; the API locks the username after 5 failures
  (15 min) and audits it. The password is never recorded.
- **The `client` is Docker's bridge gateway, not the real browser.** Behind `ssh -L` (and with Docker's userland
  proxy) Nginx's `$remote_addr` is the bridge gateway. It is the same for every tunnel user, so through the tunnel
  the per-address limit is shared. In public mode the address depends on how Docker publishes the port: with its
  default userland proxy it would be the gateway too.
  - **Follow-up before 4e:** check it on the public port, and if needed publish in `host` mode or set
    `"userland-proxy": false` on vm-095. That is a host Docker change, which needs a team decision because the
    protected deployment shares the daemon.
- **Not verified here:** a real login through the edge (it needs a person's password). The browser check of the
  original step 4: `ssh -L 18010:127.0.0.1:18010 argus-vm095`, open `http://127.0.0.1:18010`, log in, open an
  incident.

**State after this step:**
- vm-095 runs `task/T-0016-playwright` `d5d992c`: the agent with ACR-0011 4a, and `argus-v18-ui` on
  `127.0.0.1:18010`.
- vm-166 is unchanged on `main` `ad72617`.
- Back to `main` at the AFTER-MERGE of #144. If #144 is not accepted: `deploy.sh main` and `docker compose -f
  compose.ui.yml -f compose.loopback.yml down`.
