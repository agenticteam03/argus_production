-- 022: the operator console's work for the worker (ACR-0043 with T-0021, ARCHITECTURE §12.6). The API never investigates:
-- it holds no executor token and no action path, so a console read or a write proposal it ran itself failed on vm-095
-- (the target's read gateway answered 401). The API now inserts one row per read (`read`: a capability, its target
-- and arguments) or per confirmed write (`propose`: the released pair) and waits for the answer; the worker claims the
-- row, runs it with its own guarded invoke or action path and stores the result (an observation, the proposal's
-- outcome, or an error). The row moves on (queued, running, done or error), so the runtime role may UPDATE it, never
-- DELETE it. `request` and `result` hold JSON the application reads and writes whole. Additive: the old image never
-- reads it; the new API needs it (and a worker with ARGUS_OPERATOR_CONSOLE=1) to answer a console read.

CREATE TABLE console_job (
  job_id       text PRIMARY KEY,
  kind         text NOT NULL CHECK (kind IN ('read', 'propose')),
  incident_id  text NOT NULL REFERENCES incident(id),
  person       text NOT NULL,
  request      text NOT NULL,
  status       text NOT NULL CHECK (status IN ('queued', 'running', 'done', 'error')),
  claimed_by   text,
  result       text,
  requested_at timestamptz NOT NULL,
  updated_at   timestamptz NOT NULL);
CREATE INDEX console_job_queued ON console_job (requested_at) WHERE status = 'queued';

GRANT SELECT, INSERT, UPDATE ON console_job TO argus_runtime;
