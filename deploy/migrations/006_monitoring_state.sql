-- 006: the monitoring heartbeat state per host (T-0035, ARCHITECTURE §7.3, ACR-0009). One row per host: alive /
-- starting / lost, the loss episode and its incident, the last renewal seen, an optional maintenance window. Kept in
-- the database so a scheduler restart neither opens a second incident for the same episode nor forgets one. Mutable
-- state, not evidence: the transitions themselves are audited (monitoring.lost, .recovered, .maintenance).

CREATE TABLE monitoring_state (
  host       text PRIMARY KEY,
  state      jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now());

GRANT SELECT, INSERT, UPDATE ON monitoring_state TO argus_runtime;
