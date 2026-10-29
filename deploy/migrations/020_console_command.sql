-- 020: the operator console's history (ACR-0043, CON-2). One row per completed console command: its incident, the
-- person, the input as typed, the command id and class, the status, the output (cut at 4 KB, `output_truncated`) and
-- the times. `history` reads it back per incident; the read quota counts its rows. Insert-only for the runtime role:
-- SELECT and INSERT, never UPDATE or DELETE (the grants, as for link_event). Additive: the old image keeps working on
-- this schema; the new image needs the migration before it records a command.

CREATE TABLE console_command (
  command_id       text PRIMARY KEY,
  incident_id      text NOT NULL,
  person           text NOT NULL,
  input            text NOT NULL,
  command          text NOT NULL,                -- the registry id, e.g. cache.status
  cls              text NOT NULL CHECK (cls IN ('meta', 'read', 'write')),
  status           text NOT NULL CHECK (status IN ('ok', 'error', 'rejected', 'needs_confirmation')),
  output           text NOT NULL,
  output_truncated boolean NOT NULL DEFAULT false,
  suggestion_id    text,
  started_at       timestamptz NOT NULL,
  finished_at      timestamptz NOT NULL);
CREATE INDEX console_command_incident ON console_command (incident_id, started_at);
CREATE INDEX console_command_person ON console_command (person, started_at);

GRANT SELECT, INSERT ON console_command TO argus_runtime;
