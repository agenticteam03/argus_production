# ACR-0018 — Operator access and audit for privileged actions

Part of the next-phase proposal ([task](../../tasks/current/NEXT-PHASE-supervised-remediation.md)) with
[ACR-0019](ACR-0019-human-approved-remediation.md) (human-approved remediation) and
[ACR-0020](ACR-0020-operator-terminal.md) (operator terminal). This ACR is their precondition: neither may be
implemented before this one is applied and deployed.

| Field | Value |
|---|---|
| Status | `accepted` (#209, approved by `juanbetancurm`, merged 2026-10-21) (§5). Not applied: that is phase 16 |
| Proposed by | juanbetancurm (+ agent) · 2026-10-18 |
| Accepted by | a teammate approving `task/ACR-0018-accepted` (proposed there by `conantkd` · 2026-10-20) |
| Second approval (safety principle only) | **required**: least privilege (privileged routes, new permissions), secrets (new signing keys), evidence integrity (the audit chain). **Given:** `juanbetancurm`'s approval of #209 (AGENT_PROTOCOL §4: the developer accepts, a second team member approves; one teammate's approval) |
| Architecture version | the next free version when applied (1.8.22 if applied next) |
| Task / PR | NEXT-PHASE · #170 (proposed) · `task/ACR-0018-accepted` (accepted, open decisions 2, 3 and 7 answered) |

## 1. Detect and explain

The next phase lets an authenticated human **approve an action that Argus executes** (ACR-0019) or **open a full
terminal** on a VM (ACR-0020). Both are privileged writes reachable from a browser. Today's access model was designed
for a read-only UI:

- Login is a password only; the failed-login limiter lives in memory (a restart forgets it) (§17.3).
- Tokens are HS256 JWTs for 30 min; `jti` is issued but never checked, so a stolen token cannot be revoked before it
  expires; anyone holding the signing key mints any role (§17.2, §17.3).
- Permissions are three roles plus a token narrowing (`read`, `investigate`); there is no per-action permission,
  no step-up, no separation of duties (§17.3, ACR-0001, ACR-0012).
- Audit integrity rests on database permissions only ("DB permissions enforce append-only", §17.1 layer 13), in the
  same Postgres on vm-095 where every developer has sudo (`policies/SECURITY.md`).
- `policies/SECURITY.md` still lists "the team's shared Argus password", while §17.3 requires one account per person
  for every Internet-reachable login (OP-016).

An approval or a terminal session is only as trustworthy as the identity behind it and the record of it.

## 2. Why the current architecture is insufficient

- §17.1 layer 8 asks for an "authenticated **human** approver; scoped; digest-bound", but a password-only login with a
  non-revocable bearer token does not prove the human at the moment of the approval.
- §17.1 layer 13 makes audit append-only against the application, not against a host administrator.
- §14.3: "In this release the approver authenticates to the API (JWT, §17.3) and answers through Swagger or the CLI",
  on the loopback listener. Moving approvals to the UI (ACR-0019) needs a stronger path than the public edge's
  read/investigate tokens.

## 3. Smallest reasonable change

**§17.1** — layer 1 and layer 13 change; a layer 15 is added:

- Layer 1, before: "human login ⇒ short-lived JWT". After: "human login ⇒ short-lived JWT; **WebAuthn second factor
  required for any principal holding a privileged permission**; **step-up** (a fresh second factor, ≤ 5 min) for
  each privileged write".
- Layer 13, before: "DB permissions enforce append-only". After: "DB permissions enforce append-only; every audit row
  carries `prev_hash` (a per-day hash chain); a signed daily digest is shipped **off Host A**; a scheduled job verifies
  the chain".
- Layer 15 (new), "Privileged exposure": "approval answers, holds, the terminal and administration are served only on
  a private path (team VPN, or mTLS with an address allowlist); the public edge answers 404 for them".

**§17.2** — rows changed or added:

| Identity | Used by | Holds |
|---|---|---|
| Human principals | HTTP/CLI | username + Argon2 password hash **+ WebAuthn credentials**; **one per person, no shared account** |
| Token signing key | api | **EdDSA** private key (api only); other components verify with the public key; rotated by deployment |
| Session store | api | server-side session rows (`jti`, principal, created, last seen, revoked) |
| Audit digest key | scheduler (digest job) | signs the daily audit digest |

**§17.3** — additions:

- "Every request checks its `jti` against the session store; logout, a password change or an administrator's
  revocation ends the session at once."
- "**Permissions** are explicit and checked per route: `view`, `investigate`, `feedback`, `propose_action`,
  `approve_action`, `place_hold`, `open_terminal:<host>`, `admin`. A role is a bundle of permissions; principals also
  carry host/target scopes. `/me` lists the permissions; the UI shows a control only when its permission is listed."
- "**Step-up**: a privileged write needs a step-up token: single-use, ≤ 5 min, bound to the object it authorizes
  (`approval_id + proposal_digest`, `terminal ticket`, `hold`)."
- "**Separation of duties** (production profile): the principal who requested an investigation, or who is the
  incident's operator of record, cannot approve its action. The lab profile may allow it; the audit records it."
- "The failed-login limiter is persisted in Postgres."

**§18** — a line: "Security events (refused privileged requests, failed step-ups, revoked sessions) raise an alert
through the Argus-owned Alertmanager to the team's route."

**§25 OD-10** — "answering approvals stays in Swagger/CLI in this release" becomes "approvals are answered in the UI
over the private path with step-up (ACR-0018, ACR-0019)".

**Alternatives considered:**
- A: **keep password + JWT, rely on short TTLs.** Rejected: 30 min of a stolen token is enough to approve an action
  or open a shell.
- B: **an external identity provider (OIDC) now.** Better long-term (§17.3 "Future") but the team has none today;
  the permission model and step-up here carry over unchanged when OIDC replaces local users.
- C: **TOTP instead of WebAuthn.** Accepted only as a fallback: TOTP can be phished, WebAuthn cannot.
- D: **keep privileged routes on the public edge behind MFA.** Rejected: one web vulnerability would expose them;
  the private path is defence in depth.

## 4. Consequences

- **Code:** `adapters/inbound/http.py` (sessions, permissions, step-up, WebAuthn routes), `infrastructure/settings.py`,
  a migration (sessions, WebAuthn credentials, login limiter, `prev_hash` on audit), an audit digest job, `/me`.
- **Tests:** an authorization matrix (every route × role × token kind × permission); revocation within one request;
  the limiter survives a restart; step-up single-use and object-bound; the audit chain detects an edited row; the
  public edge answers 404 for every privileged route.
- **Deployment:** the private path (VPN or mTLS), the off-host digest store, new key files, the edge configuration.
- **UI:** WebAuthn enrolment and step-up dialogs; controls driven by `/me` permissions.
- **Other sections:** §7.1 (new routes), §14.3 (approvals in the UI), §16.2 (audit role unchanged; digest job role).
- **Risk:** lock-out if WebAuthn is lost (mitigation: a second registered key per person, a documented recovery by
  another administrator, audited); more moving parts at login.
- **How to reverse it:** keep MFA and sessions (they only add security); disabling the private path closes the
  privileged routes, which blocks ACR-0019 and ACR-0020 but leaves the read-only UI working.
- **Safety principles touched:** yes: least privilege, secrets, evidence integrity. Second approval required.

## 5. Decision

Proposed in #170. **Accepted** in #209 by `juanbetancurm`'s approval, which is also the second approval the safety
principles touched (least privilege, secrets, evidence integrity) ask for (AGENT_PROTOCOL §4). §3 is accepted as written. The
answers below are to the NEXT-PHASE open decisions that belong to this ACR (2, 3 and 7); the others belong to
ACR-0019 and ACR-0020.

1. **Private path (decision 2): mTLS client certificates with an address allowlist**, on the existing public edge.
   - The privileged routes are served by `argus-v18-ui` on the same `tcp/443`: no new port, no cloud rule, no
     VPN client. nginx asks for a client certificate (`ssl_verify_client optional`) and answers **404** on a
     privileged location unless the certificate verifies against the team's client CA **and** the source address is
     in the allowlist. The read-only UI keeps working without a certificate.
   - One certificate per person, short-lived (90 days), issued by a client CA whose private key never sits on
     vm-095 (only its public certificate does). Revoking a person is a CRL entry plus their Argus session revoked.
   - Not a VPN: `wg0` belongs to the protected deployment (`infrastructure/environment.md`) and is not reused, and a
     second WireGuard interface would be one more thing on both VMs that `nonint-check.sh` has to tell apart.
   - mTLS is defence in depth, not the identity: the human is still proven by WebAuthn and the step-up (§3).
2. **Permissions (decision 3):** the three enabled operators of OP-016 (`conantkd`, `juanbetancurm`, `juanes6554`)
   hold `view`, `investigate`, `feedback`, `propose_action`, `approve_action` and `place_hold`. **`admin`:**
   `conantkd` and `juanbetancurm`, so that a WebAuthn recovery is always done by another administrator (§4, risk).
   **`open_terminal:<host>`: nobody** until ACR-0020 is accepted; that ACR decides it. The disabled principals
   (`conantkd-viewer`, `olav`) get nothing new. Every grant and revocation is an audited row.
   **Separation of duties:** enforced on the production profile, as in §3. On the lab profile it is **allowed and
   recorded**: with three operators, enforcing it would often leave nobody to approve; the audit row and the UI mark
   a self-approval, and the scheduled evaluation counts them.
3. **Off-host store (decision 7):** an object-storage bucket outside both VMs, with versioning and a write-once
   retention lock, written through a **put-only** credential that cannot delete or overwrite (a new secret under
   `secrets/agent/`, never printed). Not vm-166 and not a developer's laptop: every developer has sudo on both VMs,
   and a laptop is one person's. **Retention:** audit digests 1 year; terminal recordings 90 days (ACR-0020 may
   change the latter). The provider is chosen by whoever administers the cloud account when phase 16 is deployed,
   and recorded in `policies/NETWORK.md` with the other egress (§6). Until the bucket exists, phase 16 cannot be
   deployed: the digest job fails closed and raises the security alert of §18.

Next: phase 16 applies this ACR, with its first code, in one pull request (§6).

## 6. Applied

Applied in steps (phase 16). Each step writes into `ARCHITECTURE.md` only what it builds; the rest of §3 stays
"designed".

**Step 1** (`task/PHASE-16-step-1-sessions`, ARCHITECTURE 1.8.26):
- [x] server-side sessions (`auth_session`, migration 010) checked on every request; `POST /api/v1/auth/logout`;
      revocation by `argus user add|disable` and `argus session revoke` (audited)
- [x] `POST /api/v1/auth/logout` also through the public edge (`deploy/ui/nginx/locations.conf`, `contracts/ui-api.json`);
      the UI's sign-out calls it before forgetting the token (best effort: an older API's 404, an ended session or no
      network still forget it)
- [x] a correctly signed token without a live session of its own is audited (`security.session_refused`)
- [x] the failed-login limiter persisted (`login_failure`)
- [x] permissions per route, a role as a bundle, listed by `/me` (only the permissions of built routes)
- [x] the audit hash chain (migration 011): one chain over all rows in write order (`seq`), each row's `hash` over the
      previous hash, its id and its canonical body; an advisory lock per row so concurrent writers never fork it;
      `argus audit verify`, and the scheduler's check at start and daily (`audit_chain` in `schedules.yaml`), recorded
      as `security.audit_chain_verified` / `security.audit_chain_broken`. **As built, not per day:** one continuous chain is simpler to verify and stronger; the
      daily digest of §3 becomes "the hash of each day's last row", signed and shipped once the off-host store exists
- [x] tests: `tests/test_acr0018_sessions.py` (sessions, revocation, forged and foreign `jti`, the lockout across a
      restart), `tests/test_acr0018_authz_matrix.py` (**the authorization matrix**: every route × role × token kind against
      a declared table, 401 without a token, and every route of the API must be in the table; red seen by weakening the
      evidence route), `tests/test_acr0018_audit_chain.py` (an edited,
      removed or foreign row is named), `tests/test_postgres.py` (grants of 010; 40 concurrent writers, one chain; an
      owner who disables the trigger and edits a row is caught)
- [x] journal entry (`2026-10-21-PHASE-16-step-1.md`)

- [x] EdDSA token signing: with the secret `jwt_ed25519_key` (an Ed25519 PEM) the API signs EdDSA and accepts only
      EdDSA; without it, HS256 as before. `PyJWT[crypto]`. `policies/SECURITY.md` names the new secret. Switching the
      lab on is a deploy step (generate the key on vm-095, never printed; every session logs in again)
- [x] `auth_session` retention (#240): `argus db prune-sessions`, owner-only, preview unless `--apply`, sessions whose
      token expired more than 90 days ago; audited `maintenance.sessions_pruned`. Maintenance audit rows are written
      chained (`append_chained`), so a prune never breaks `argus audit verify`
- [ ] step 2: the agent mounts `jwt_ed25519_key` (`deploy/vm-095/compose.core.yml`); the key generated on vm-095
      before `up` (`execution/history/PHASE-16/step-02/code.bash`)

- [x] step 3 (1.8.29): WebAuthn (`webauthn==3.0.1`, D1) and the step-up token: migration 013; the relying party
      is the UI's DNS name (D2); two credentials per privileged person and a reset by the other administrator (D3);
      the first credential by another administrator's ticket (D4); privileged permissions only after this login's
      second factor; the routes through the public edge; `tests/test_acr0018_webauthn.py` (a software authenticator).
      The step-up's binding to approvals comes with ACR-0019's routes (phase 17); the UI dialogs are step 3b

- [x] step 4 (1.8.30): the private path. Privileged routes under `/api/v1/ops/` (a test keeps them there); the
      edge passes the prefix only for a client certificate of the team's CA, not revoked, from an allowlisted address,
      else 404; the CA (`ops/edge-ca.sh`, its key encrypted on a laptop, a copy with the other administrator), the
      allowlist (`ops/edge-allow.sh`, named entries with an expiry, a daily prune, addresses never in Git); off until
      `ARGUS_OPS_PATH=on`; `policies/NETWORK.md`; `tests/test_phase16_private_path.py` (the real Nginx with mTLS)

- [x] step 5a (1.8.32): the signed daily digest. `domain/audit_digest.py` (the digest of a closed UTC day: the last
      chained row, its hash, the row count; Ed25519 signature over the canonical JSON; a check against the chain),
      `infrastructure/audit_digest.py` (`AuditDigestJob`: verify the chain, sign nothing if it is broken, put each
      closed day once, never overwrite a different object; every outcome a `security.audit_digest_*` event),
      `adapters/outbound/digest_sinks.py` (`LocalDirSink`, which says it is not off host), `audit_digest` in
      `deploy/scheduler/schedules.yaml` (off), `ARGUS_AUDIT_DIGEST_SINK`; `tests/test_phase16_step5_digest.py`.
      Not built in 5a: the OCI sink (5b), the key on vm-095 and the schedule turned on (5c)

- [x] step 5b (1.8.33): the OCI sink. `OciObjectSink` (`adapters/outbound/digest_sinks.py`): a digest is created once
      with `If-None-Match: *`, its SHA-256 as object metadata, and, when the service refuses, a HEAD tells whether the
      name holds the same bytes (the credential cannot read a body); `DigestSinkError` carries a status and a code, never
      the service's message. `ARGUS_AUDIT_DIGEST_SINK=oci:<namespace>/<bucket>`, the credential in `oci_digest/config` and
      `key.pem` under the secrets folder; `oci==2.189.0`; `tests/test_phase16_step5b_oci_sink.py`, with an opt-in test
      against a real bucket. The bucket and its permissions were proved by hand on 2026-10-23 (§5)

- [x] step 5c (1.8.34), **prepared, not deployed**: the digest key and the OCI credential are on vm-095 in
      `/opt/argus-v18/secrets/digest/` (generated and copied on 2026-10-23, never printed; evidence
      `execution/history/PHASE-16/step-05c-prep`); the scheduler mounts them read-only and no other service does
      (`compose.core.yml`, `mem_limit` 256m), `ARGUS_AUDIT_DIGEST_SINK` from `hosts.env`; `argus audit check-digests
      <files> --public-key <pem>` checks shipped digests as a series against the chain; `policies/NETWORK.md` names
      OCI Object Storage as the scheduler's one outbound destination. `audit_digest` stays `enabled: false` until a
      first run has been checked after the deploy; `tests/test_phase16_step5c_check.py`

**Not yet** (step 5b on): separation of duties; the deploy of step 5c, a first checked run and the schedule turned on; security alerts (§18), which wait for the team's alert route (no receiver exists: Argus only reads its
Alertmanager), including the alert on `security.audit_chain_broken`;
`policies/SECURITY.md` (the new secrets).
