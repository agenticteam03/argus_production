-- 007: re-check lineage (ACR-0021, T-0045 B5). An incident may name the incident it re-checks (`parent_id`). The
-- parent must exist (foreign key) and the link never changes: the forward-only trigger of 001 now also refuses a new
-- `parent_id`, like the incident's other identity columns. No new grant: the runtime role already inserts and updates
-- incident rows (001); still no DELETE. ACR-0021's `deploy_event` (B7) is a later migration.

ALTER TABLE incident ADD COLUMN parent_id text NULL REFERENCES incident (id);
CREATE INDEX incident_parent ON incident (parent_id, opened_at DESC);

CREATE OR REPLACE FUNCTION argus_incident_forward_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id <> OLD.id OR NEW.target <> OLD.target OR NEW.opened_at <> OLD.opened_at
     OR NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
    RAISE EXCEPTION 'incident % identity is immutable', OLD.id;
  END IF;
  IF OLD.status IN ('closed', 'escalated') AND NEW.status <> OLD.status THEN
    RAISE EXCEPTION 'incident % is % (final); cannot become %', OLD.id, OLD.status, NEW.status;
  END IF;
  RETURN NEW;
END $$;
