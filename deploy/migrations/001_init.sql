-- 001_init — Argus v1.8 system of record (Phase 5). Applied once by ops/db-migrate.sh as the database owner,
-- inside one transaction. The agent connects as argus_runtime, which can never UPDATE/DELETE evidence or audit.

CREATE TABLE incident (
  id              text PRIMARY KEY,
  target          text NOT NULL,
  status          text NOT NULL CHECK (status IN ('queued', 'running', 'closed', 'escalated')),
  opened_at       timestamptz NOT NULL,
  idempotency_key text UNIQUE,
  body            jsonb NOT NULL);
CREATE INDEX incident_status ON incident (status, opened_at);
CREATE INDEX incident_target ON incident (target, opened_at DESC);

CREATE TABLE evidence (
  evidence_id  text PRIMARY KEY,
  incident_id  text NOT NULL REFERENCES incident (id),
  collected_at timestamptz NOT NULL,
  host         text,
  executor     text,
  sha256       text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  body         jsonb NOT NULL);
CREATE INDEX evidence_incident ON evidence (incident_id, collected_at);

CREATE TABLE audit (
  audit_id    text PRIMARY KEY,
  incident_id text,
  at          timestamptz NOT NULL,
  body        jsonb NOT NULL);
CREATE INDEX audit_incident ON audit (incident_id, at);

CREATE TABLE principal (
  id            text PRIMARY KEY,
  kind          text NOT NULL,
  role          text NOT NULL,
  scopes        jsonb NOT NULL,
  password_hash text NOT NULL,
  disabled      boolean NOT NULL DEFAULT false);

CREATE TABLE run_event (
  incident_id text NOT NULL,
  seq         integer NOT NULL,
  at          timestamptz NOT NULL,
  node        text NOT NULL,
  phase       text NOT NULL,
  data        jsonb NOT NULL,
  PRIMARY KEY (incident_id, seq));

CREATE TABLE notification (
  key     text PRIMARY KEY,
  at      timestamptz NOT NULL,
  payload jsonb NOT NULL);

-- Evidence, audit and run events are insert-only — for EVERY role, including the owner.
CREATE FUNCTION argus_insert_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is insert-only', TG_TABLE_NAME;
END $$;
CREATE TRIGGER evidence_insert_only BEFORE UPDATE OR DELETE ON evidence FOR EACH ROW EXECUTE FUNCTION argus_insert_only();
CREATE TRIGGER evidence_no_truncate BEFORE TRUNCATE ON evidence FOR EACH STATEMENT EXECUTE FUNCTION argus_insert_only();
CREATE TRIGGER audit_insert_only BEFORE UPDATE OR DELETE ON audit FOR EACH ROW EXECUTE FUNCTION argus_insert_only();
CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit FOR EACH STATEMENT EXECUTE FUNCTION argus_insert_only();
CREATE TRIGGER run_event_insert_only BEFORE UPDATE OR DELETE ON run_event FOR EACH ROW EXECUTE FUNCTION argus_insert_only();

-- Incidents move forward only: identity never changes, and a closed/escalated incident is final.
CREATE FUNCTION argus_incident_forward_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id <> OLD.id OR NEW.target <> OLD.target OR NEW.opened_at <> OLD.opened_at THEN
    RAISE EXCEPTION 'incident % identity is immutable', OLD.id;
  END IF;
  IF OLD.status IN ('closed', 'escalated') AND NEW.status <> OLD.status THEN
    RAISE EXCEPTION 'incident % is % (final); cannot become %', OLD.id, OLD.status, NEW.status;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER incident_forward_only BEFORE UPDATE ON incident FOR EACH ROW EXECUTE FUNCTION argus_incident_forward_only();

-- Runtime role: least privilege. No DELETE anywhere; no UPDATE on evidence/audit/run_event; no DDL.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'argus_runtime') THEN
    CREATE ROLE argus_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO argus_runtime;
GRANT SELECT, INSERT, UPDATE ON incident, principal TO argus_runtime;
GRANT SELECT, INSERT ON evidence, audit, run_event, notification TO argus_runtime;
