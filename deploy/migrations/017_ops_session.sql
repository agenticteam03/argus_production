-- 017: the private browser login's session (ACR-0032, phase 19). `ops` is a full token that the API accepts only on
-- the private path (the edge's X-Argus-Ops). It ends after 15 minutes without a request (last_seen_at) and one hour
-- after the login at most (expires_at). The access CHECK of auth_session (010) widens; the runtime role may also set
-- last_seen_at (a column-level UPDATE grant), besides the revocation (010) and second-factor (013) columns.

ALTER TABLE auth_session DROP CONSTRAINT auth_session_access_check;
ALTER TABLE auth_session ADD CONSTRAINT auth_session_access_check
  CHECK (access IN ('full', 'read', 'investigate', 'ops'));
ALTER TABLE auth_session ADD COLUMN last_seen_at timestamptz;
GRANT UPDATE (last_seen_at) ON auth_session TO argus_runtime;
