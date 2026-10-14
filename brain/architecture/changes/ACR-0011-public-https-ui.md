# ACR-0011 — The read-only UI on a public HTTPS address (Nginx on vm-095:443)

An Architecture Change Record is the **only** way to change `brain/architecture/ARCHITECTURE.md`. ACRs are never
fast-tracked. This one touches two safety principles (least privilege: a public listener; secrets: a TLS private
key), so it needs **a second approval** in its pull request.

| Field | Value |
|---|---|
| Status | `proposed` — implemented and applied in PR #144 (ARCHITECTURE 1.8.10, T-0016 step 4a–4c); accepted only when #144 has a teammate's approval **and** the second approval (one approval so far: `juanes6554`, on #140) |
| Proposed by | conantkd (+ agent) · 2026-10-13 |
| Accepted by | — |
| Second approval (safety principle only) | required: least privilege and secrets (§4) |
| Architecture version | from `1.8.8` → `1.8.10` (1.8.9 is reserved by ACR-0010), or the next free number when applied |
| Task / PR | T-0016 step 4 (rewritten by this ACR, §7) · proposal #140, implementation #144 |

**How to read the facts below.** **(O)** observed with a command on 2026-10-13 (read-only), **(D)** documented in the
repository, **(S)** assumed: to be confirmed before implementation. The team confirmed that HTTPS to the VM *can* be
enabled; that does **not** mean the port is open today **(O: it is not)**. Nothing here is implemented or deployed.

## 1. Detect and explain

The team wants users to open Argus's read-only UI **in a browser, from a URL, without an SSH account**. Today the
only way in is an SSH tunnel to a loopback port, which needs an SSH key on vm-095 for every user.

Decision of the team, the input to this ACR:

```text
https://argus.<domain>
        ↓
vm-095:443 — Nginx (container argus-v18-ui)
        ├── /          → the compiled React frontend
        └── /api/v1/…  → only the UI contract's routes of Argus's internal API
```

- Nginx receives the public connections.
- Argus keeps authentication and authorization: the existing Argus login with read tokens, and **no mandatory second
  gate**.
- No ngrok and no Cloudflare Tunnel.

What exists today:

| Fact | Kind | Source |
|---|---|---|
| The UI is a separate, read-only client of the API; tokens with `scope=read` are refused on every non-`GET` route (403, audited) | D, O (code) | ACR-0001; §17.3; `argus/adapters/inbound/http.py` |
| The planned UI container `argus-v18-ui` serves the built files and proxies `/api/` on **`127.0.0.1:18010`**, reached with `ssh -L` | D | T-0016 step 4; §25 OD-10 |
| The API listens on `127.0.0.1:18000` on the host; inside `argus-v18-core` it is `argus-v18-agent:8000` (API) and `:8001` (webhook) | D, O | `deploy/vm-095/compose.core.yml`; `argus/__main__.py` |
| Argus ports are `18000–18799`, **bound to `127.0.0.1` only, "never `0.0.0.0` or a public address"** | D | `infrastructure/environment.md` §3 |
| "Human → Argus API: HTTP(S) over a loopback-bound SSH tunnel or VPN"; Swagger "served only on the loopback listener"; layer 7: "no public exposure" | D | ARCHITECTURE §3.3, §7.1, §17.1, §17.3 |
| The cloud firewall leaves only SSH open from outside, and "the team cannot change" the cloud network rules (no cloud console) | D | `environment.md` §1 |
| vm-095 has **no public address on any interface**: one private interface plus Docker bridges, so a public address reaches it through the provider's NAT (S) | O | `ip -4 addr`, classified only (no address printed) |
| Nothing listens on `:80` or `:443`; non-loopback listeners are only `:22` and `:111` (rpcbind) | O | `ss -ltn` |
| Host firewall `INPUT`: ESTABLISHED, ICMP, `lo` and **tcp/22 accepted, everything else REJECT**; `DOCKER-USER` empty; no `ufw` | O | `iptables -S` |
| A **Docker-published port does not traverse `INPUT`** (DNAT then `FORWARD`), so the `INPUT` reject above would not protect a published `:443` | D | Docker's iptables model |
| vm-095 is `aarch64`, 1 vCPU, 5.9 GB RAM, no swap; no nginx, certbot or caddy on the host or in its images | O, D | `uname -m`; `environment.md` §1 |
| A protected, separate Argus deployment runs on vm-095 (`/opt/argus`, compose project `argus`); `nonint-check` snapshots non-Argus listeners **and firewall rules** | D | `environment.md` §4 |
| `POST /api/v1/auth/token`: **no rate limit, no lockout, no audit of a failed login**; §17.3 says "Failed logins are rate-limited and audited (`access.login_failed`)" | O (code), D | `http.py`; no `login_failed` anywhere in `argus/` |
| A login **without** `scope=read` gets a **full** token (`access: "full"`), which may `POST /api/v1/investigations` | O (code) | `http.py` |
| FastAPI serves `/docs` and `/openapi.json` on the same app as `/api/v1/…` | O (code) | `build_api` |
| `GET /api/v1/incidents?limit=` has **no upper bound**; the frontend asks for `limit=1000` every 5 s | O (code) | `http.py`; `frontend/src/utils/paging.js` (`INCIDENTS_CAP = 1000`) |
| Principals on vm-095: **3 active humans, all `operator`** (so all see evidence and audit); "the team's shared Argus password" is a documented secret | O, D | `principal` table (counts only); `policies/SECURITY.md` |
| A real-mode build (`VITE_ARGUS_MOCK=0`) **ships every runbook** (24 Markdown files, imported with `import.meta.glob`) **and the mock adapter with the demo password** in public JS (640 KB) | O | build of `main` after #137, `grep` of `dist/assets` |
| The runbooks are generic SRE procedures; one names the two hosts, one shows `sudo`/`docker` commands; no secret values | O | `grep` of `argus/runbooks/` |

## 2. Why the current architecture is insufficient

- **§3.3 / §3.6 / §7.1:** humans reach the API only "over a loopback-bound SSH tunnel or VPN", which needs an SSH
  account per user: the opposite of the goal.
- **§17.1 layer 7:** "no public exposure", and **`environment.md` §3:** "never `0.0.0.0` or a public address". A
  public `:443` is a deliberate exception to both, so it needs an ACR and a second approval.
- **§25 OD-10 (ACR-0001):** `argus-v18-ui` on "a loopback port of Host A, reached like Swagger (SSH tunnel)".
- **§17.3** promises a login rate limit and an audit of failed logins that the code does not have (§1). Behind an SSH
  tunnel that gap was harmless. On a public address it means unlimited password guessing, and Argon2 makes each
  guess cost CPU on a 1-vCPU VM.
- **ACR-0001** keeps a UI read-only by the client's choice of `scope=read`. A public login form lets **any client**
  ask for a full token. The proxy must keep the public path read-only by itself.

## 3. Smallest reasonable change

### 3.1 The design

| # | Topic | Proposal |
|---|---|---|
| 1 | Name and DNS | One subdomain `argus.<domain>` with an `A` record to the **public address mapped to vm-095** (pending, §8). The domain and the address are configuration (`/opt/argus-v18/hosts.env`, `deploy/ui/vm-095.env`), **never in Git or the Brain** (`SECURITY.md` rule 4). |
| 2 | Network | Cloud rule: inbound **tcp/443** to vm-095 (and **tcp/80** only for an HTTP-01 certificate, row 4) from the Internet, opened by whoever administers the cloud network (pending, §8). Host: the container publishes `0.0.0.0:443` (and `:80`). Because published ports bypass `INPUT`, the host rule goes in **`DOCKER-USER`**: accept new `tcp/443` (and `/80`) only toward `argus-v18-ui`, tagged `argus-v18`, and leave every other rule untouched (protected `wg0` rules included). This is the single exception to "loopback only": one container, two ports, nothing else. |
| 3 | UI container | `argus-v18-ui`: a multi-stage image (`node:24` builds with `VITE_ARGUS_MOCK=0`, then `nginx:1.x-alpine`, multi-arch for `aarch64`), the built files in `/usr/share/nginx/html`, React routes by `try_files $uri /index.html`. It joins `argus-v18-core` to reach `argus-v18-agent:8000`; no other network and no volume except the certificate (read-only). Response headers: HSTS, a `Content-Security-Policy` with `default-src 'self'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; `server_tokens off`. |
| 4 | Certificate | Let's Encrypt (public, free, 90 days). **HTTP-01** by the webroot of `argus-v18-ui` on `:80`. Port 80 serves only `/.well-known/acme-challenge/` and a 301 to HTTPS. If `:80` cannot be opened, use **DNS-01** with the DNS provider's API token instead (pending, §8). Issued and renewed by a `certbot` container from a daily systemd timer `argus-v18-certbot.timer`, with `nginx -s reload` after a renewal. Stored in `/opt/argus-v18/secrets/tls/` (0700 root; the key 0600), mounted read-only. An alert when the certificate has less than 14 days left. |
| 5 | What the proxy publishes | **An allowlist built from `contracts/ui-api.json`:** `POST /api/v1/auth/token`; `GET /api/v1/me`, `/incidents`, `/incidents/{id}`, `/incidents/{id}/events`, `/evidence/{id}`, `/escalations`. Each `location` limits its method (`limit_except`). **Everything else is 404 at Nginx**: `/docs`, `/openapi.json`, `POST /api/v1/investigations`, any approval route, `/metrics`, and the webhook port `:8001`, which is never proxied. Swagger stays on the loopback listener (§7.1 unchanged). A test keeps the Nginx allowlist and the contract equal. |
| 6 | Login and authorization | Argus keeps them. **New in the API:** (a) when a login arrives through the proxy (Nginx always **sets** a header such as `X-Argus-Edge: public` and removes any copy from the client), the API **issues only read tokens**: a login without `scope=read` gets 400 there, while the loopback login is unchanged; (b) the §17.3 promise implemented: failed logins audited (`access.login_failed`, username and client address, never the password) and rate-limited per username and per address, with a short lockout; (c) `limit` on `GET /incidents` capped server-side (for example 200). **Before going public:** one account per person with its own password (no shared password on a public form), and the least role each needs (`viewer` where evidence and logs are not needed). The token TTL stays 30 min; the UI's 8 h session TTL (#137) is bounded by it. |
| 7 | Responsibilities | **Nginx:** TLS, static files, the route allowlist, request limits, access logs. **API:** authentication, authorization, audit. **Worker, scheduler, Postgres:** no listener reachable from the edge (unchanged). Nginx never holds an Argus secret, only the TLS key. |
| 8 | Load | Nginx `limit_req`: login about 5 per minute per address (burst 5), the API about 10 per second per address (burst 20). `limit_conn` per address, `client_max_body_size 8k`, short timeouts. UI polling: dashboard and incident list every 15–30 s instead of 5 s, paused while the tab is hidden; the incident list asks for at most the server cap. |
| 9 | Public and private content | **Public:** the static bundle. A real-mode build must **not** contain the mock adapter or the demo password (dropped at build time). **The runbooks become private:** taken out of the bundle and served by Nginx under `/runbooks/` only to a request whose bearer token passes an `auth_request` to `GET /api/v1/me`, so the UI loads them after login and the API contract stays as it is. The alternative, keeping them public, needs an explicit team decision. **Private:** incidents, diagnoses, evidence (log excerpts, already redacted, §10.8) and audit, only through the authenticated API; evidence and audit only for `operator`/`approver`. No source maps; `contracts/samples/` is never deployed. Access logs never record `Authorization` or the login body. |
| 10 | Verification, observability, rollback | **Before the merge:** `nginx -t` in CI; the allowlist-equals-contract test; tests for the new API rules (edge login read-only, `login_failed`, rate limit, `limit` cap); a build test that the bundle has no mock adapter and no runbook. **At deploy:** a curl matrix from outside: `/` 200; an unknown route 200 (SPA); `/docs` 404; `POST /api/v1/investigations` 404; `/api/v1/me` 401 without a token; HTTP 301 to HTTPS; a valid certificate chain and the headers above; a login with and without `scope=read`; `nonint-check` NO INTERFERENCE, with its firewall snapshot taught to ignore rules tagged `argus-v18`. **Observability:** Nginx JSON access and error logs, 4xx/5xx and `login_failed` counts, certificate days left. **Rollback:** `docker compose stop argus-v18-ui`, remove the `DOCKER-USER` rules, and close the cloud rule. The loopback API and the SSH-tunnel path keep working throughout. |

### 3.2 `ARCHITECTURE.md`, before → after (the minimal text)

- **§3.3, the row "Human → Argus API"**, before: *"HTTP(S) over a loopback-bound SSH tunnel or VPN"*. After: *"the
  read-only UI over **public HTTPS** (`argus-v18-ui` on Host A:443, an allowlist of the UI contract, read tokens
  only; ACR-0011); the CLI and Swagger over a loopback-bound SSH tunnel or VPN"*.
- **§3.4** (diagram), **§3.5** (container inventory: `argus-v18-ui`) and **§3.6** (API exposure): the same.
- **§7.1 Listeners**, one sentence added: *"The public edge (`argus-v18-ui`, ACR-0011) proxies only the routes of
  `contracts/ui-api.json` with their methods; a login through it issues only read tokens; Swagger and every other
  route stay on the loopback listener."*
- **§17.1 layer 7**, before: *"no public exposure"*. After: *"no public exposure except the UI edge of ACR-0011
  (TLS, route allowlist, rate limits)"*. **A new layer "Public edge"** with the Nginx controls of §3.1, rows 5 and 8.
- **§17.3:** the read-only edge login; the failed-login rule made concrete (per user and per address, with lockout,
  audited `access.login_failed`); "one account per person" for any login reachable from the Internet.
- **§20.1:** `ARGUS_EDGE_HEADER`, the login rate limits and the `limit` cap.
- **§25 OD-10:** *"… runs as `argus-v18-ui` … on a loopback port of Host A"* → *"… on a public HTTPS address of
  Host A (ACR-0011); the loopback path stays for development and recovery"*.
- **Changelog** `1.8.10` with this ACR's link.

**Alternatives considered:**
- **A — Keep the SSH tunnel** (`ssh -L 18010`). This is the current design: it needs an SSH account per user, which
  is what the team wants to remove.
- **B — A VPN** (WireGuard or similar) **for users.** Every user needs a client and a key. The `wg0` interface on
  vm-095 is a protected object of another deployment, so a second VPN means new UDP exposure plus key management.
  Heavier than one HTTPS port for a read-only view.
- **C — ngrok or Cloudflare Tunnel.** Excluded by the team: traffic and TLS would end at a third party.
- **D — A mandatory second gate** (HTTP basic auth, mTLS, an IP allowlist). Not mandatory, by the team's decision:
  one account per person, the read-only edge login and the rate limits are the controls. An IP allowlist stays an
  **optional** Nginx setting if the users' networks are known; it costs nothing to keep ready.
- **E — Caddy instead of Nginx** (automatic certificates, TLS-ALPN-01 on 443 only). Simpler certificates, but the
  team chose Nginx, and T-0016 step 4 and `RB-015` already speak Nginx. Kept as a fallback if `:80` can never be
  opened and DNS-01 is not possible.
- **F — Expose the API port directly** (no Nginx). This would publish `/docs`, `/openapi.json` and every route, with
  no rate limit. Rejected.

## 4. Consequences

- **Code:**
  - `deploy/ui/`: Dockerfile, `nginx.conf`, compose, env template, the certbot timer.
  - The API: the edge login rule, `access.login_failed` with its rate limit, the `limit` cap. These are
    `adapters/inbound/http` only; the domain, use cases, policy and tools are untouched.
  - The frontend: no mock code in a real build, the runbooks loaded after login, the polling intervals.
  - `ops/nonint-check.sh`: ignore the rules tagged `argus-v18`.
  - Tests: the edge, the API rules and the bundle contents.
- **Deployment:** one new container and two public ports on vm-095; one cloud rule; one DNS record; one
  certificate; one systemd timer. vm-166 is unchanged.
- **Other documents:** see §6.
- **Risk:**
  - Internet exposure of a login form and of read data: incidents, diagnoses, redacted log excerpts.
  - A load spike on a 1-vCPU VM that also runs the agent, Postgres and a protected deployment.
  - A misconfigured allowlist that publishes a route.
  - Mitigations: §3.1 rows 5, 6, 8 and 10, and the "before going public" account rule.
  - Residual: credential theft from a user (no second factor). It is bounded by read-only tokens, a 30-minute TTL
    and the per-user `disabled` flag, checked on every request.
- **How to reverse it:** stop `argus-v18-ui`, remove the `DOCKER-USER` rules, close the cloud rule, delete the DNS
  record; revert the ARCHITECTURE text. Nothing in the core depends on the edge.
- **Safety principle touched? Yes:**
  - **least privilege**: a public listener, an exception to "loopback only";
  - **secrets**: a TLS private key on vm-095, to be added to `SECURITY.md`'s table.
  - Read-only, the write gate, host isolation and evidence integrity are unchanged; the public path is narrower than
    today's loopback login.
  - **A second approval is required.**

## 5. Decision

Proposed by `conantkd` on 2026-10-13 from the team's decision above. Waiting for a teammate's acceptance **and** a
second approval. Until then nothing in §3 is built. The pending data of §8 must be answered before step 4b of T-0016.

## 6. Documents to update after acceptance

| Where | What |
|---|---|
| `brain/architecture/ARCHITECTURE.md` | §3.3, §3.4, §3.5, §3.6, §7.1, §17.1 (layer 7 + public edge), §17.3, §20.1, §25 OD-10, changelog |
| `brain/infrastructure/environment.md` | §1: the cloud rule for 443/80 and who manages it. §2: the topology with `argus-v18-ui`. §3: the port rule with its single exception (`argus-v18-ui` `0.0.0.0:443`, `:80`). §4: the `nonint-check` firewall exclusion for `argus-v18` rules |
| `brain/policies/SECURITY.md` | the secrets table (the TLS key; the DNS API token if DNS-01); rule 4 (the domain and the public address stay out of Git); one account per person for a public login |
| `docs/API-FOR-UI.md` | production is served by the public edge; login through it is read-only; the `limit` cap; the runbooks path |
| `contracts/ui-api.json` | unchanged, unless the `limit` cap is declared in the schema (a contract change, reviewer sees the diff) |
| `frontend/README.md`, `GUIDELINES.md` | the polling intervals; runbooks after login; no mock code in a real build |
| `brain/tasks/current/T-0016-frontend.md` | step 4 as in §7 |
| `ops/nonint-check.sh` | the `argus-v18` firewall-rule exclusion |

## 7. T-0016 step 4, rewritten (proposal)

The rewritten step is in `brain/tasks/current/T-0016-frontend.md`, under "Step 4 — proposed by ACR-0011". It replaces
the loopback step only after acceptance.

## 8. Pending data (before building)

1. **The domain** and who administers its DNS: can they create `argus.<domain>`, and is there an API token for
   DNS-01?
2. **The public address that reaches vm-095** and that the provider maps it to the VM (O: no public address on its
   interfaces). **Known since 2026-10-14** (`conantkd`; kept out of Git, rule 4): from the
   Internet tcp/22 answers, and tcp/80 and tcp/443 time out (O, from a laptop). A timeout is the cloud network
   dropping them; the host's `INPUT` would refuse at once. A certificate needs a **name** (`argus.<domain>` with an
   `A` record to it): Let's Encrypt's IP certificates are a 6-day profile that needs a newer ACME client.
3. **Who opens tcp/443 (and tcp/80)** in the cloud network rules (D: "the team cannot change" them today), and
   whether :80 may be opened for HTTP-01.
4. **Existing services on 443:** none listens on vm-095 (O). Confirm that the provider, or another workload behind
   the same public address, does not use 443/80 there.
5. **Certificates:** Let's Encrypt is acceptable? (the alternative is a certificate the organization already has,
   with its renewal owner).
6. **The users:** who gets an account, and with which role (`viewer` or `operator`).

## 9. Applied (PR #144, waiting for the approvals)

- [x] `ARCHITECTURE.md` 1.8.10: §3.3, §3.5, §3.6, §7.1, §17.1 (layer 7, new layer 14), §17.3, §20.1, OD-10, changelog
- [x] `environment.md`, `SECURITY.md`, `docs/API-FOR-UI.md` (§6 of this ACR)
- [x] T-0016 4a (API), 4b (frontend), 4c (the edge image, its scripts and tests). Not done: 4d on vm-095 (loopback,
      needs the lease) and 4e (public, needs the data of §8)
- [x] journal entry

**Two differences from §3.1, found while building:**
- **Row 2:** Docker already forwards a published port only to its container, so an "accept only toward
  argus-v18-ui" rule would add nothing. `ops/ui-firewall.sh` instead puts a per-address connection limit (50) on the
  edge's ports in `DOCKER-USER`.
- **Row 10:** `nonint-check` already leaves out Docker's chains, so it needs no firewall exclusion. What it learns
  instead is to leave out the ports `argus-v18-ui` publishes while it runs.
