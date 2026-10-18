# ACR-0018 — Operator access and audit for privileged actions

Part of the next-phase proposal ([task](../../tasks/current/NEXT-PHASE-supervised-remediation.md)) with
[ACR-0019](ACR-0019-human-approved-remediation.md) (human-approved remediation) and
[ACR-0020](ACR-0020-operator-terminal.md) (operator terminal). This ACR is their precondition: neither may be
implemented before this one is applied and deployed.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-18 |
| Accepted by | pending (team review of the NEXT-PHASE proposal PR) |
| Second approval (safety principle only) | **required**: least privilege (privileged routes, new permissions), secrets (new signing keys), evidence integrity (the audit chain) |
| Architecture version | the next free version when applied (1.8.17 if applied first) |
| Task / PR | NEXT-PHASE · PR (this proposal) |

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

Proposed. To be accepted or changed in the NEXT-PHASE proposal PR review; the open decisions (VPN vs mTLS, the
off-host store, who holds which permission) are listed in the task file.

## 6. Applied

- [ ] `ARCHITECTURE.md` updated, version bumped, changelog line added (with this ACR's link)
- [ ] `policies/SECURITY.md` (one account per person, new secrets, the principle text) and `policies/NETWORK.md`
      (the private path, the off-host destination)
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
