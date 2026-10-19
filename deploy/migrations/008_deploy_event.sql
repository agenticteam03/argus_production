-- 008: deploy events (ACR-0021, T-0045 B7). One row per deploy of a commit to a host, written by `argus deploy record`
-- (which `ops/deploy.sh` calls after `DEPLOY OK`), read by the incident charts as `deploy` events. Insert-only for the
-- runtime role: SELECT and INSERT, never UPDATE or DELETE (the grants, as for evidence and audit). The spec named this
-- "migration 007 part 2"; B5 took 007 for `incident.parent_id`.

CREATE TABLE deploy_event (
  id          bigserial PRIMARY KEY,
  host        text NOT NULL,
  commit_sha  text NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{7,40}$'),
  ref         text NOT NULL,
  actor       text NOT NULL,
  at          timestamptz NOT NULL);
CREATE INDEX deploy_event_host ON deploy_event (host, at);

GRANT SELECT, INSERT ON deploy_event TO argus_runtime;
GRANT USAGE ON SEQUENCE deploy_event_id_seq TO argus_runtime;
