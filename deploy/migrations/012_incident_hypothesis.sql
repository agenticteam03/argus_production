-- 012: the hypotheses of an investigation (ACR-0024 §3.5, T-0047 H2). One row per hypothesis per decision step, with
-- the evidence ids it cites and the score and rank Argus computed (application/ranking.py), never the model. Read by
-- the incident answer (T-0047 H3) and the evaluation (H4). Insert-only for the runtime role: SELECT and INSERT, never
-- UPDATE or DELETE (the grants, as for evidence and audit).

CREATE TABLE incident_hypothesis (
  id             bigserial PRIMARY KEY,
  incident_id    text NOT NULL REFERENCES incident (id),
  step           integer NOT NULL CHECK (step >= 1),      -- the decision step that stated it
  hypothesis_id  text NOT NULL CHECK (hypothesis_id ~ '^h[1-5]$'),
  statement      text NOT NULL,
  cause_class    text NOT NULL,                           -- an incident class name, or "other"
  target         text,                                    -- null only for an external cause
  relation       text NOT NULL CHECK (relation IN ('self', 'dependency', 'host', 'external')),
  status         text NOT NULL CHECK (status IN ('supported', 'ruled_out', 'untested')),
  support_ids    text[] NOT NULL DEFAULT '{}',
  against_ids    text[] NOT NULL DEFAULT '{}',
  score          double precision NOT NULL,
  rank           integer NOT NULL CHECK (rank >= 1),
  chosen         boolean NOT NULL DEFAULT false,
  at             timestamptz NOT NULL,
  UNIQUE (incident_id, step, hypothesis_id));
CREATE INDEX incident_hypothesis_incident ON incident_hypothesis (incident_id, step);

GRANT SELECT, INSERT ON incident_hypothesis TO argus_runtime;
GRANT USAGE ON SEQUENCE incident_hypothesis_id_seq TO argus_runtime;
