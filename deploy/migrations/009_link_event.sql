-- 009: link-state transitions (ACR-0025, T-0046 L2). One row per change of a declared dependency link's state, written
-- by the scheduler's reconcile tick (T-0046 L3) from the exporter's existing probes, and once per link at startup; read
-- by the map (`since`) and the incident charts (T-0046 L4). Insert-only for the runtime role: SELECT and INSERT, never
-- UPDATE or DELETE (the grants, as for deploy_event).

CREATE TABLE link_event (
  id          bigserial PRIMARY KEY,
  owner       text NOT NULL,              -- the target ref that depends, e.g. vm-166/container:argus-lab-api
  dependency  text NOT NULL,              -- the target ref it depends on, on the same host
  state       text NOT NULL CHECK (state IN ('ok', 'slow', 'broken', 'unknown')),
  latency_ms  double precision,           -- the probe's answer time; null when unknown
  reason      text,                       -- a broken link's reason (T-0045 B8); null otherwise
  at          timestamptz NOT NULL);
CREATE INDEX link_event_owner ON link_event (owner, at);
CREATE INDEX link_event_dependency ON link_event (dependency, at);

GRANT SELECT, INSERT ON link_event TO argus_runtime;
GRANT USAGE ON SEQUENCE link_event_id_seq TO argus_runtime;
