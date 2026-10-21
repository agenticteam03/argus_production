-- 010: server-side sessions and the persisted login limiter (ACR-0018, phase 16 step 1).
-- auth_session: one row per issued token (its jti). Every request checks it, so logout, a password change or an
-- administrator's revocation ends a session at once instead of at the token's expiry. The runtime role inserts a
-- session and may set ONLY its revocation columns (a column-level UPDATE grant); it never deletes one.
-- login_failure: the failed-login counts that were in memory (a restart forgot them). The runtime role inserts a
-- failure and deletes a user's failures after a successful login; nothing else.

CREATE TABLE auth_session (
  jti            text PRIMARY KEY CHECK (jti ~ '^[0-9a-f]{32}$'),
  principal      text NOT NULL,
  access         text NOT NULL CHECK (access IN ('full', 'read', 'investigate')),
  created_at     timestamptz NOT NULL,
  expires_at     timestamptz NOT NULL,
  revoked_at     timestamptz,
  revoked_by     text,
  revoke_reason  text);
CREATE INDEX auth_session_principal ON auth_session (principal, created_at);

CREATE TABLE login_failure (
  id   bigserial PRIMARY KEY,
  key  text NOT NULL,                  -- 'u:<username>' or 'a:<client address>'
  at   timestamptz NOT NULL);
CREATE INDEX login_failure_key ON login_failure (key, at);

GRANT SELECT, INSERT ON auth_session TO argus_runtime;
GRANT UPDATE (revoked_at, revoked_by, revoke_reason) ON auth_session TO argus_runtime;
GRANT SELECT, INSERT, DELETE ON login_failure TO argus_runtime;
GRANT USAGE ON SEQUENCE login_failure_id_seq TO argus_runtime;
