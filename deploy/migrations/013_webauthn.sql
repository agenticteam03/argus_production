-- 013: WebAuthn second factor and the step-up token (ACR-0018, phase 16 step 3; D1-D4 in the PHASE-16 task).
-- webauthn_credential: one registered authenticator per row. The runtime role inserts one, updates only its sign
--   counter and last use, and revokes it (an administrator's reset); it never deletes or rebinds one.
-- webauthn_challenge: every ceremony's challenge, server-side, single-use (used_at) and short-lived (expires_at).
-- webauthn_enrol_ticket: D4, the first credential's ticket issued by another administrator; only its SHA-256 is kept.
-- step_up_token: a fresh second factor bound to one principal, session and object; only its SHA-256 is kept.
-- auth_session.second_factor_at: when this session's login was completed with a credential.
-- None of these rows is ever deleted by the runtime role.

ALTER TABLE auth_session ADD COLUMN second_factor_at timestamptz;
GRANT UPDATE (second_factor_at) ON auth_session TO argus_runtime;

CREATE TABLE webauthn_credential (
  id            text PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9_-]{16,}$' AND length(id) <= 1366),   -- base64url
  principal     text NOT NULL,
  public_key    bytea NOT NULL,                                             -- COSE, from the attestation
  sign_count    bigint NOT NULL CHECK (sign_count >= 0),
  label         text NOT NULL DEFAULT '',
  created_at    timestamptz NOT NULL,
  last_used_at  timestamptz,
  revoked_at    timestamptz,
  revoked_by    text);
CREATE INDEX webauthn_credential_principal ON webauthn_credential (principal) WHERE revoked_at IS NULL;

CREATE TABLE webauthn_challenge (
  id          text PRIMARY KEY CHECK (id ~ '^wch_[0-9a-f]{32}$'),
  principal   text NOT NULL,
  session     text NOT NULL,
  kind        text NOT NULL CHECK (kind IN ('register', 'login', 'step_up')),
  challenge   bytea NOT NULL,
  object      text,                                                       -- step_up: what it will authorize
  ticket      text,                                                       -- register: the enrolment ticket used
  created_at  timestamptz NOT NULL,
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz);

CREATE TABLE webauthn_enrol_ticket (
  id          text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{64}$'),             -- SHA-256 of the code shown once
  principal   text NOT NULL,
  issued_by   text NOT NULL CHECK (issued_by <> principal),               -- nobody issues their own
  created_at  timestamptz NOT NULL,
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz);

CREATE TABLE step_up_token (
  id          text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{64}$'),             -- SHA-256 of the token
  principal   text NOT NULL,
  session     text NOT NULL,
  object      text NOT NULL,
  created_at  timestamptz NOT NULL,
  expires_at  timestamptz NOT NULL CHECK (expires_at <= created_at + interval '5 minutes'),
  used_at     timestamptz);

GRANT SELECT, INSERT ON webauthn_credential TO argus_runtime;
GRANT UPDATE (sign_count, last_used_at, revoked_at, revoked_by) ON webauthn_credential TO argus_runtime;
GRANT SELECT, INSERT ON webauthn_challenge, webauthn_enrol_ticket, step_up_token TO argus_runtime;
GRANT UPDATE (used_at) ON webauthn_challenge, webauthn_enrol_ticket, step_up_token TO argus_runtime;
