-- 021: Argus's analysis of an operator-console command (ACR-0043, CON-4b). One row per console command that is analysed:
-- the metric snapshot taken when the command started, the samples taken after its settle delay, and Argus's result (a
-- grounded comment, the evidence it cited, the ranking recomputed from it, a validated suggestion, or the error). The
-- history of a command (console_command, migration 020) stays insert-only; this row changes while the analysis runs
-- (waiting, analyzing, done or error) and when a person asks for a re-check, so the runtime role may UPDATE it, never
-- DELETE it. `body` holds the JSON the application reads and writes whole. Additive: the old image never reads it.

CREATE TABLE console_analysis (
  command_id  text PRIMARY KEY REFERENCES console_command(command_id),
  incident_id text NOT NULL REFERENCES incident(id),
  status      text NOT NULL CHECK (status IN ('waiting', 'analyzing', 'done', 'error')),
  body        text NOT NULL,
  updated_at  timestamptz NOT NULL);
CREATE INDEX console_analysis_incident ON console_analysis (incident_id);

GRANT SELECT, INSERT, UPDATE ON console_analysis TO argus_runtime;
