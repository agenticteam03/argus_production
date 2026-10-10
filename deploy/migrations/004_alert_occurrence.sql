-- 004: alert occurrences (OP-011, ARCHITECTURE §6.4 and §5.2). Every firing alert that opened (`started`) or joined
-- (`attached`) an incident, keyed by its trigger identity (fingerprint + startsAt, §6.6), so the same alert in a later
-- pass is a `duplicate` of its incident even when it did not open it. The incident's evidence version is
-- 1 + its attached occurrences; its last evidence time is the newest occurrence. Insert-only for the runtime role
-- (resolution, which needs UPDATE of `status`, comes with resolved alerts).

CREATE TABLE alert_occurrence (
  identity     text PRIMARY KEY,
  incident_id  text NOT NULL REFERENCES incident (id),
  fingerprint  text NOT NULL,
  starts_at    timestamptz NOT NULL,
  alertname    text NOT NULL DEFAULT '',
  labels       jsonb NOT NULL,
  disposition  text NOT NULL CHECK (disposition IN ('started', 'attached')),
  status       text NOT NULL DEFAULT 'firing' CHECK (status IN ('firing', 'resolved')),
  received_at  timestamptz NOT NULL);
CREATE INDEX alert_occurrence_incident ON alert_occurrence (incident_id, received_at);

GRANT SELECT, INSERT ON alert_occurrence TO argus_runtime;
