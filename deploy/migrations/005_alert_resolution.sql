-- 005: resolved alerts (T-0026, ARCHITECTURE §6.4 "Resolution", ACR-0005). An alert occurrence goes from `firing` to
-- `resolved` when its resolved notification arrives (push) or when it is absent from a successful read of its host's
-- active alerts (pull). The runtime role may update only those two columns, only forward (a trigger refuses any other
-- change): the occurrence's identity, incident, labels and times stay as recorded. Still no DELETE.

ALTER TABLE alert_occurrence ADD COLUMN resolved_at timestamptz;

CREATE FUNCTION argus_alert_occurrence_resolve_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status <> 'firing' OR NEW.status <> 'resolved' OR NEW.resolved_at IS NULL THEN
    RAISE EXCEPTION 'alert_occurrence: only firing -> resolved, with resolved_at';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER alert_occurrence_resolve_only BEFORE UPDATE ON alert_occurrence
  FOR EACH ROW EXECUTE FUNCTION argus_alert_occurrence_resolve_only();

GRANT UPDATE (status, resolved_at) ON alert_occurrence TO argus_runtime;
