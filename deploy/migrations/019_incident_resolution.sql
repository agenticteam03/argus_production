-- 019: a person may close an escalated incident that was fixed outside Argus (ACR-0041). Migration 007's forward-only
-- rule stays, with one exception: `escalated` may become `closed` once, and only when the new body carries the
-- person's `resolution` (who, when, why). Every other change of a final status is still refused, and an incident's
-- identity still never changes. No new grant: the runtime role already updates incident rows (001); still no DELETE.

CREATE OR REPLACE FUNCTION argus_incident_forward_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id <> OLD.id OR NEW.target <> OLD.target OR NEW.opened_at <> OLD.opened_at
     OR NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
    RAISE EXCEPTION 'incident % identity is immutable', OLD.id;
  END IF;
  IF OLD.status = 'escalated' AND NEW.status = 'closed'
     AND jsonb_typeof(NEW.body->'resolution') = 'object'
     AND coalesce(jsonb_typeof(OLD.body->'resolution'), 'null') = 'null' THEN
    RETURN NEW;                                   -- ACR-0041: resolved by a person, once
  END IF;
  IF OLD.status IN ('closed', 'escalated') AND NEW.status <> OLD.status THEN
    RAISE EXCEPTION 'incident % is % (final); cannot become %', OLD.id, OLD.status, NEW.status;
  END IF;
  RETURN NEW;
END $$;
