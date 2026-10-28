-- 018: a judge's `doubt` lets a person decide (ACR-0039, amending ACR-0019 §3.8's phase 18 reading and migration 016).
-- An approval row may be created, and moved to `approved`, when a stored judge verdict `agree` OR `doubt` binds the
-- proposal's digest and does not forbid the action; a `disagree`, another digest, a forbidden colour or no verdict at
-- all are still refused here. The trigger keeps its name; only its function changes. The runtime role's grants do not
-- change (it already reads judge_verdict).

CREATE OR REPLACE FUNCTION approval_needs_agree() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP = 'INSERT' OR NEW.state = 'approved') AND NOT EXISTS (
       SELECT 1 FROM judge_verdict v
        WHERE v.proposal_id = NEW.proposal_id AND v.verdict IN ('agree', 'doubt')
          AND v.body->>'proposal_digest' = NEW.proposal_digest
          AND coalesce(v.body->>'risk', '') <> 'forbidden') THEN
    RAISE EXCEPTION 'an approval needs the judge''s agree or doubt on this proposal';
  END IF;
  RETURN NEW;
END $$;
