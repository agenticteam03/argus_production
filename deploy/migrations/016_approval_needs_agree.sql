-- 016: an approval needs the judge's `agree` on its exact proposal (ACR-0019 §3.8, phase 18 review of #323).
-- The application already refuses to request or answer one without it; the database now refuses too: no approval
-- row is created, and none moves to `approved`, unless a stored judge verdict `agree` binds the proposal's digest
-- and does not forbid the action. The runtime role's grants do not change (it already reads judge_verdict).

CREATE FUNCTION approval_needs_agree() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP = 'INSERT' OR NEW.state = 'approved') AND NOT EXISTS (
       SELECT 1 FROM judge_verdict v
        WHERE v.proposal_id = NEW.proposal_id AND v.verdict = 'agree'
          AND v.body->>'proposal_digest' = NEW.proposal_digest
          AND coalesce(v.body->>'risk', '') <> 'forbidden') THEN
    RAISE EXCEPTION 'an approval needs the judge''s agree on this proposal';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER approval_needs_agree BEFORE INSERT OR UPDATE ON approval
  FOR EACH ROW EXECUTE FUNCTION approval_needs_agree();
