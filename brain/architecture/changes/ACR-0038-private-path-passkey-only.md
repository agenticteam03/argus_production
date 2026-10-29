# ACR-0038 — Private path: a passkey-only mode, off by default

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | `conantkd` · 2026-10-28 |
| Accepted by | `conantkd` · 2026-10-28 |
| Second approval (safety principle only) | not required |
| Architecture version | proposed: `1.8.45` → `1.8.46` |
| Task / PR | private path access · PR to be numbered on opening |

## 1. Problem

Approving an action needs four proofs: the edge's client certificate (a `.p12` installed in the browser, ACR-0018 phase 16 step 4 and ACR-0037), the private login (a password, for a human approver with two WebAuthn credentials, ACR-0032), a session completed with a security key, and a step-up with a key for each decision. Installing and renewing the certificate on every approver's browser, every 90 days, is the step that blocks approvers; the two security keys already prove the person.

## 2. Why the current architecture is insufficient

The edge decides `$argus_ops_ok` from `$ssl_client_verify` alone, so without the certificate the whole private path is 404, however strong the rest of the proof. There is no way to run with the keys alone, and no record of which proof an approver used.

## 3. Smallest reasonable change

- `ARGUS_OPS_PASSKEY_ONLY=off|on` on the edge, **off by default**; `on` needs `ARGUS_OPS_PATH=on`; any other value stops the edge.
- `$argus_ops_ok` is defined by exactly one of two files, which the edge's start script copies to `conf.d`:
  - `ops-mode-certificate.conf` (the default, unchanged behaviour): a verified, unrevoked team certificate;
  - `ops-mode-passkey.conf`: any TLS request; the plain-HTTP loopback server stays 0.
- In passkey-only mode the certificate is not asked for and the CA files are not needed. The switch covers the whole `/api/v1/ops/` prefix and an `ops` token's runbook reads (both use `$argus_ops_ok`).
- The API is unchanged in what it requires: the private login refuses anyone who is not a human approver with two credentials, an `ops` token has no privileged permission until its session is completed with a key, and every decision needs a step-up bound to it. A test now states that a password alone reaches no privileged route.
- The edge sends `X-Argus-Ops-Cert: $ssl_client_verify` (replacing any browser copy); the private login (`access.login`, `access.ops_login_failed`) and each approval answer (`action.approval_answered`) record `client_cert: verified | none`, believed only on the private path from the edge itself.

**Alternatives considered:**

- Remove the certificate outright: rejected; the mode is reversible by one variable and the default stays the stronger one.
- Apply the switch only to the approval routes: rejected by the owner; holds, the emergency stop, corpus decisions and runbook reads follow the same rule.

## 4. Consequences

- Code and tests: `deploy/ui/nginx/http.conf`, `ops-mode-certificate.conf`, `ops-mode-passkey.conf`, `proxy.conf`, `deploy/ui/05-argus-mode.envsh`, `compose.public.yml`, `vm-095.env.example`; `argus/adapters/inbound/http.py`, `argus/infrastructure/wiring.py`; the private login text in the UI; tests in `test_phase16_private_path.py` (the real Nginx in both modes and the start script), `test_phase19_private_login.py`, `test_acr0011_ui_edge.py`, `test_incident_action_trail.py`.
- Deployment: none by this change. Turning it on: `ARGUS_OPS_PASSKEY_ONLY=on` in `deploy/ui/vm-095.env` and recreate `argus-v18-ui` (lease).
- Risk when on: the private login is reachable from the internet, without the device proof. It is still limited and locked out per user and per address, audited and alerted on refusal, and useless without the person's security keys; every decision still needs a key. A stolen password is not enough; stolen keys are revoked with the second-factor administration.
- Reversal: set the variable back to `off` (or remove it) and recreate the edge.
- Safety principle changed: no. The read-only phase, the write gate, the judge and the human approval with a step-up are unchanged; one defence-in-depth layer becomes optional.

## 5. Decision

`conantkd` asked for it on 2026-10-28: approving actions needs the two security keys, not the browser certificate, with the mode off until it is turned on, covering the whole private path and the runbooks, with the proof recorded in the audit.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped to 1.8.46, changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the code that needs it are in the same pull request
