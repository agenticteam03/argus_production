# PHASE-16 — Operator access and audit (ACR-0018), step by step

| Field | Value |
|---|---|
| Status | `in progress` — step 1 merged (#223) and deployed on vm-095 (DEPLOY-A4479DF, 2026-10-21); steps 2–6 planned below |
| Phase | 16 of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md) ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md) (`accepted`, #209); each step applies only what it builds (its §6) |
| Branch | one per step: `task/PHASE-16-step-<n>-<slug>` |
| Owner | `conantkd` (+ agent); review `juanbetancurm` |
| Needs the VM lease | the deploy of each step (vm-095) |

## Goal

An approval (ACR-0019) or a terminal (ACR-0020) is only as trustworthy as the identity behind it and the record of
it. Phase 16 ends when the exit proof of the plan holds: the authorization matrix is green, the public edge answers
404 for every privileged route, and an edited audit row is detected.

## Steps

### Step 1 — sessions, revocation, persisted login limiter, permissions, audit chain, EdDSA (#223)
Merged (#223) and deployed on vm-095 at `a4479df`: [`../../execution/history/DEPLOY-A4479DF/step-01/evidence.md`](../../execution/history/DEPLOY-A4479DF/step-01/evidence.md) (prepared as [`../../execution/history/PHASE-16/step-01/code.bash`](../../execution/history/PHASE-16/step-01/code.bash))
(prepared: migrations 010 and 011, the image, the checks; run after #223 merges).

### Step 1b — `auth_session` retention (`task/PHASE-16-session-retention`)
`argus db prune-sessions` (owner-only, a read-only preview unless `--apply`): removes sessions whose token expired more
than 90 days ago (`ARGUS_SESSION_RETENTION_DAYS`), audited as `maintenance.sessions_pruned`. Its audit row and
`prune-checkpoints`' are now written chained (`append_chained`): a bare INSERT after migration 011 would have broken
`argus audit verify` at the first checkpoint prune that removed anything. First dry run with step 2's deploy.

### Step 2 — EdDSA switched on in the lab
- Generate the Ed25519 key **on vm-095** (`openssl genpkey -algorithm ed25519`), owned like `jwt_signing_key`,
  never printed; then add its single-file mount to the agent in `deploy/vm-095/compose.core.yml` in the same PR.
  **Order matters:** a bind mount of a missing file makes Docker create a directory there, and the API would not
  start; the code.bash creates the file before `up`.
- Every session logs in again (old HS256 tokens are refused). A rollback is removing the mount.

### Step 3 — WebAuthn and step-up
- **Open decisions:** the library (`webauthn` / py_webauthn, pinned, `pip-audit` clean); the relying party id (the
  UI's public domain, which is not in Git); two keys per person and the recovery by another administrator (§4, risk).
- A migration: `webauthn_credential` (principal, credential id, public key, sign count, created, last used), insert
  plus a sign-count update for the runtime role.
- Routes: registration options / verify, authentication options / verify. A **step-up token**: single-use, ≤ 5 min,
  bound to the object it authorizes (`approval_id + proposal_digest`, a terminal ticket, a hold); a used or expired
  one is refused and audited.
- UI: enrolment and the step-up dialog (frontend lane, `juanes6554`).
- Tests: a software authenticator for the ceremonies; replay of a step-up token; the wrong object; the sign counter.

#### Step 3 — decisions (proposed 2026-10-21, decided 2026-10-22)
Found while preparing: **the lab's public UI is served on an IPv4 address** (`ARGUS_UI_DOMAIN` on vm-095 is an
address, with Let's Encrypt's 6-day IP certificate; checked without printing it). **WebAuthn cannot use an address as
its relying party id**: browsers refuse it. So D2 blocks the step; D1 and D3 do not.

| # | Decision | Options | Proposal |
|---|---|---|---|
| D1 | The library | `webauthn` (py_webauthn, Duo Labs) / write the ceremonies by hand | **`webauthn==3.0.1`** (released 2026-09-25, BSD-3, no advisory recorded for any version; its crypto is `cryptography`, already a dependency; adds `cbor2`, `pyasn1`, `pyasn1-modules`, `pyOpenSSL`). Pinned, `pip-audit` in CI as today. |
| D2 | The relying party id (blocker) | (a) a DNS name for the UI, kept in `vm-095.env` like `ARGUS_UI_DOMAIN` (never in Git); (b) `localhost` through the SSH tunnel to the loopback UI (`compose.loopback.yml`), privileged actions only there; (c) a wildcard-DNS name for the address (`<address>.sslip.io` style) | **(a)** for anything past the lab: phishing resistance is the reason for WebAuthn over TOTP (ACR-0018 §3, option C), and it holds only with a real name. **(b) as the lab's interim**: it works today (a browser treats `http://localhost` as secure), matches step 4's idea (privileged routes off the public edge) and needs no purchase; its cost: a credential is bound to `localhost`, so it moves to the real name later (re-enrolment). (c) rejected: a third party's DNS decides who the relying party is. |
| D3 | Keys per person, recovery | one key / two keys; recovery by the person / by another administrator | **Two registered credentials per privileged person** (e.g. a platform passkey and a security key); a privileged permission is refused until two exist. **Recovery** by the other administrator (`conantkd` ↔ `juanbetancurm`, §4): an `argus webauthn reset <user> --as <admin>` CLI on vm-095 (the lease holder, like `argus session revoke`), audited `security.webauthn_reset`, which also revokes the user's sessions. |

**Decided 2026-10-22 (`conantkd`):** D1 as proposed (`webauthn==3.0.1`). **D2 (a):** the UI is served by a DNS name
(the team's subdomain, kept in `deploy/ui/vm-095.env` as `ARGUS_UI_DOMAIN`, never in Git), resolved straight to vm-095
(no CDN proxy: a proxy would end TLS and see every password and token), with its own Let's Encrypt certificate (90
days, HTTP-01 through the edge, renewed by the existing timer); the address now redirects to the name
([evidence](../../execution/history/D2-ui-domain/step-01/evidence.md)). The relying party id and the expected origin
are that name, read from the VM's environment like `ARGUS_UI_DOMAIN`. No re-enrolment is foreseen: (b)'s
`localhost` interim is not needed. D3 as proposed (two credentials per privileged person; recovery by the other
administrator through an audited CLI that revokes the user's sessions).
**D4 (new, decided 2026-10-22, `conantkd`): the first credential.** A password alone must not bind a key: whoever
stole it could enrol theirs before the owner. (a) **An enrolment ticket from the other administrator**: `argus
webauthn allow-enrol <user> --as <admin>` on vm-095 (the lease holder), single-use, valid
`ARGUS_WEBAUTHN_ENROL_TICKET_HOURS` (default 24) or until used, audited `security.webauthn_enrol_allowed`; nobody
issues their own. The second credential is enrolled with a step-up of the first. Rejected: (b) a free first enrolment
while the person has no key (the gap above, even with an alert); (c) the first enrolment through the `localhost`
tunnel only (a credential bound to `localhost` does not work on the name). The keys themselves do not expire; a new
ticket is needed only after a reset (both keys lost).

Also for the code (no decision needed): the expected origin is checked with its port; the challenge is server-side,
single-use, ≤ 5 min; the sign counter refuses a clone (a counter that goes back); the step-up token's object
(`approval_id + proposal_digest`) waits for ACR-0019's routes, so step 3 builds enrolment, login's second factor and a
step-up bound to a test object, with the binding to approvals added in phase 17.

### Step 4 — the private path (mTLS) and separation of duties
- The team's client CA, its private key off vm-095; one 90-day certificate per person; a CRL.
- `deploy/ui/nginx/`: `ssl_verify_client optional`; privileged locations answer 404 unless the certificate verifies
  **and** the source address is in the allowlist. The allowlist is a file under `/opt/argus-v18/` on vm-095 with a
  template in the repo, **never the addresses** (Juan's note on #209: a teammate's home address is personal data).
- `policies/NETWORK.md`; a test that the public edge answers 404 for every privileged route.
- Separation of duties: refused on the production profile, recorded and marked in the lab (needs the approval routes
  of ACR-0019; the rule and its test come with them). `config/policy.yaml`'s profile is decided here (ACR-0027).

### Step 5 — the off-host digest and security alerts
- **Open decisions:** the bucket's provider (versioned, retention-locked, a put-only credential, outside both VMs);
  the team's alert receiver (none exists: Argus only reads its Alertmanager).
- The daily digest: the hash of each day's last chained audit row, signed (the audit digest key, §17.2) and shipped;
  the scheduler's chain check (built in step 1) raises the alert on `security.audit_chain_broken`, on lockouts and on
  refused privileged requests.

### Step 6 — exit proof
The authorization matrix over every route × role × token kind × permission; the public 404 test; a tamper drill on
vm-095 (an owner edits a row; `argus audit verify` and the scheduled check name it); the record.

## Not in this phase
Approvals and actions (ACR-0019, phase 17 on), the operator terminal (ACR-0020, phase 21), OIDC (§17.3 "Future").
