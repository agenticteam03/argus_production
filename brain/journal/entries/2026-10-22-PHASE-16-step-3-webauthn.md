## 2026-10-22 - PHASE-16 step 3a: the WebAuthn second factor and the step-up token (ARCHITECTURE 1.8.29)

Type: work (security)
Who: conantkd (+ agent)
Context: ACR-0018 requires a WebAuthn second factor for any privileged permission and a single-use, object-bound
step-up for a privileged write. D1-D4 were decided today (#276): `webauthn==3.0.1`, the UI's DNS name as the relying
party, two credentials per privileged person with a reset by the other administrator, and the first credential only
with another administrator's ticket.
Decision / result:
- Migration 013: `webauthn_credential`, `webauthn_challenge`, `webauthn_enrol_ticket` and `step_up_token`, plus
  `auth_session.second_factor_at`. The runtime role inserts and updates only the counters, the use and the revocation
  columns, and deletes nothing. A step-up token longer than 5 minutes and a self-issued ticket are refused by the
  database too. SQLite has the same tables with no-delete triggers. `argus db check` gains 11 checks.
- `argus/application/second_factor.py` (py_webauthn):
  - enrolment: the first credential with a ticket (a one-time code kept as its SHA-256, 24 h or until used, for its
    own person); a further one with a step-up for `webauthn.register:<user>`;
  - login: completing it with a credential marks the session;
  - step-up: issue and consume, single-use, at most 5 minutes, for that principal, session and object;
  - reset by the other administrator: the keys revoked and the sessions ended.
  - Every challenge is server-side, single-use and expires in 5 minutes; user verification is required; a counter
    that does not grow is refused as a clone. Every refusal is audited, never with a code or token.
- `http.py`: the six ceremony routes and `GET /api/v1/auth/webauthn/credentials`, allowed to every token (the UI's
  are read or investigate ones). `PRIVILEGED_PERMISSIONS` count only for a login completed with a credential and a
  person with two (none is granted yet). `/me` adds `second_factor` and the `manage_second_factor` action.
- The public edge proxies the seven routes in the API rate zone; the UI contract is regenerated (only `me.json`'s
  sample changed: `second_factor`). `argus webauthn allow-enrol|reset <user> --as <admin>` (never the user).
- The relying party id and the origin come from `ARGUS_WEBAUTHN_RP_ID` and `ARGUS_WEBAUTHN_ORIGIN` (hosts.env on
  vm-095); unset, the routes answer 503. ARCHITECTURE 1.8.29 (§1 layer 1, §7.1, §17.3, the changelog), ACR-0018 §6.
Consequences: no privileged permission exists yet, so nobody's access changes; the binding of a step-up to an
approval comes with ACR-0019's routes (phase 17). Next: 3b (the UI dialogs), then the deploy (migration 013 before the
image, the two variables, a ticket for each administrator from the other).
References: [PHASE-16](../../tasks/current/PHASE-16-operator-access.md),
[ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md), #276.

### Test state

PHASE-16 step 3a: `tests/test_acr0018_webauthn.py` 16 passed (a software authenticator: ECDSA P-256, "none"
attestation, real ceremonies). The tests cover the ticket (single-use, own person, expiry), a further key by step-up,
a login marking its own session only, privileged permissions only with two keys and this login, and the step-up token
(replay, another object, session or person, expiry). They also cover the challenges (replay, another ceremony,
expiry), another origin or relying party, a counter going back, another person's key, the reset, read and investigate
tokens, and no-delete tables. `tests/test_postgres.py::test_webauthn_and_step_up_migration_013` passes on a
throwaway Postgres 16, as does `argus db check`'s list (11 new checks). The authorization matrix declares the seven routes.
The read-token sweep exempts the ceremonies like logout. The full offline suite was run; its four failures, a Postgres
regex limit and three tests to update, are fixed. Ruff is clean.
