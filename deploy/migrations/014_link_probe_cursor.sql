-- T-0046: retain the last probe sample processed per declared link so missed scheduler ticks and restarts can replay
-- Prometheus history. The runtime role may insert/read cursors and advance only state/time; link identity is fixed.

CREATE TABLE link_probe_cursor (
  owner       text NOT NULL,
  dependency  text NOT NULL,
  state       text NOT NULL CHECK (state IN ('ok', 'slow', 'broken', 'unknown')),
  at          timestamptz NOT NULL,
  PRIMARY KEY (owner, dependency));

CREATE FUNCTION link_probe_cursor_monotonic() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.at < OLD.at THEN
    RAISE EXCEPTION 'link_probe_cursor cannot move backwards';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER link_probe_cursor_monotonic BEFORE UPDATE ON link_probe_cursor
  FOR EACH ROW EXECUTE FUNCTION link_probe_cursor_monotonic();

GRANT SELECT, INSERT ON link_probe_cursor TO argus_runtime;
GRANT UPDATE (state, at) ON link_probe_cursor TO argus_runtime;
