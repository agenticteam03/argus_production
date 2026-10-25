-- 014: Phase 18 supervised-remediation proposals and approvals (ACR-0019, §14).
-- The runtime role can insert and read proposals; it cannot alter or delete them.
-- It can insert/read approvals and perform only a forward, one-time answer.
-- No action gateway is deployed and write_gate.open remains empty.

CREATE TABLE action_proposal (
  proposal_id text PRIMARY KEY,
  incident_id text NOT NULL REFERENCES incident(id),
  capability text NOT NULL,
  target text NOT NULL,
  digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
  body jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL CHECK (expires_at > created_at)
);
CREATE INDEX action_proposal_incident ON action_proposal(incident_id, created_at);
GRANT SELECT, INSERT ON action_proposal TO argus_runtime;

CREATE TABLE judge_verdict (
  proposal_id text PRIMARY KEY REFERENCES action_proposal(proposal_id),
  model_id text NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('agree','doubt','disagree')),
  body jsonb NOT NULL,
  reviewed_at timestamptz NOT NULL
);
GRANT SELECT, INSERT ON judge_verdict TO argus_runtime;

CREATE TABLE approval (
  approval_id text PRIMARY KEY,
  proposal_id text NOT NULL UNIQUE REFERENCES action_proposal(proposal_id),
  proposal_digest text NOT NULL CHECK (proposal_digest ~ '^[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN ('pending', 'approved', 'denied', 'expired', 'cancelled')),
  actor text,
  requested_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL CHECK (expires_at > requested_at),
  answered_at timestamptz,
  CHECK ((state = 'pending' AND actor IS NULL AND answered_at IS NULL)
      OR (state <> 'pending' AND answered_at IS NOT NULL))
);
CREATE INDEX approval_pending ON approval(state, expires_at) WHERE state = 'pending';

CREATE FUNCTION approval_insert_checked() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.state <> 'pending' OR NEW.actor IS NOT NULL OR NEW.answered_at IS NOT NULL
     OR NEW.proposal_digest <> (SELECT digest FROM action_proposal WHERE proposal_id = NEW.proposal_id)
     OR NEW.expires_at <> (SELECT expires_at FROM action_proposal WHERE proposal_id = NEW.proposal_id) THEN
    RAISE EXCEPTION 'approval must begin pending and bind the frozen proposal';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER approval_insert BEFORE INSERT ON approval
  FOR EACH ROW EXECUTE FUNCTION approval_insert_checked();

CREATE FUNCTION approval_forward_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.state <> 'pending' OR NEW.state NOT IN ('approved','denied','expired','cancelled')
     OR NEW.proposal_id <> OLD.proposal_id OR NEW.proposal_digest <> OLD.proposal_digest
     OR NEW.requested_at <> OLD.requested_at OR NEW.expires_at <> OLD.expires_at
     OR NEW.answered_at IS NULL
     OR (NEW.state IN ('approved','denied') AND (NEW.actor IS NULL OR NEW.answered_at >= OLD.expires_at)) THEN
    RAISE EXCEPTION 'approval transition is not forward-only';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER approval_forward BEFORE UPDATE ON approval
  FOR EACH ROW EXECUTE FUNCTION approval_forward_only();
GRANT SELECT, INSERT ON approval TO argus_runtime;
GRANT UPDATE (state, actor, answered_at) ON approval TO argus_runtime;

-- An approval and its notification are created together by the application.
CREATE TABLE notification_outbox (
  key text PRIMARY KEY,
  channel text NOT NULL,
  payload jsonb NOT NULL,
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  next_attempt_at timestamptz NOT NULL,
  last_result text,
  delivered_at timestamptz
);
CREATE FUNCTION notification_outbox_forward_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.key <> OLD.key OR NEW.channel <> OLD.channel OR NEW.payload <> OLD.payload
     OR OLD.delivered_at IS NOT NULL OR NEW.attempts <= OLD.attempts THEN
    RAISE EXCEPTION 'notification outbox is forward-only';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER notification_outbox_forward BEFORE UPDATE ON notification_outbox
  FOR EACH ROW EXECUTE FUNCTION notification_outbox_forward_only();
GRANT SELECT, INSERT ON notification_outbox TO argus_runtime;
GRANT UPDATE (attempts, next_attempt_at, last_result, delivered_at) ON notification_outbox TO argus_runtime;

CREATE TABLE resume_intent (
  approval_id text PRIMARY KEY REFERENCES approval(approval_id),
  incident_id text NOT NULL REFERENCES incident(id),
  decision text NOT NULL CHECK (decision IN ('approved','denied','expired','cancelled')),
  state text NOT NULL CHECK (state IN ('pending','done','failed')),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_outcome text
);
CREATE FUNCTION resume_intent_insert_checked() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.state <> 'pending' OR NEW.decision <> (SELECT state FROM approval WHERE approval_id = NEW.approval_id)
     OR NEW.incident_id <> (SELECT p.incident_id FROM approval a
                            JOIN action_proposal p USING (proposal_id)
                            WHERE a.approval_id = NEW.approval_id) THEN
    RAISE EXCEPTION 'resume intent does not match the answered approval';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER resume_intent_insert BEFORE INSERT ON resume_intent
  FOR EACH ROW EXECUTE FUNCTION resume_intent_insert_checked();
CREATE FUNCTION resume_intent_forward_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.approval_id <> OLD.approval_id OR NEW.incident_id <> OLD.incident_id
     OR NEW.decision <> OLD.decision OR OLD.state <> 'pending'
     OR NEW.state NOT IN ('pending','done','failed') OR NEW.attempts <= OLD.attempts THEN
    RAISE EXCEPTION 'resume intent is forward-only';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER resume_intent_forward BEFORE UPDATE ON resume_intent
  FOR EACH ROW EXECUTE FUNCTION resume_intent_forward_only();
GRANT SELECT, INSERT ON resume_intent TO argus_runtime;
GRANT UPDATE (state, attempts, last_outcome) ON resume_intent TO argus_runtime;

CREATE TABLE action (
  action_id text PRIMARY KEY,
  proposal_id text NOT NULL REFERENCES action_proposal(proposal_id),
  approval_id text NOT NULL UNIQUE REFERENCES approval(approval_id),
  state text NOT NULL CHECK (state IN ('unstarted','attempting','confirmed','failed','indeterminate')),
  attempted_at timestamptz,
  result_at timestamptz,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE FUNCTION action_insert_checked() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.state NOT IN ('unstarted','attempting')
     OR NEW.proposal_id <> (SELECT proposal_id FROM approval WHERE approval_id = NEW.approval_id)
     OR (SELECT state FROM approval WHERE approval_id = NEW.approval_id) <> 'approved'
     OR (NEW.state = 'attempting' AND NEW.attempted_at IS NULL) THEN
    RAISE EXCEPTION 'action must bind an approved frozen proposal';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER action_insert BEFORE INSERT ON action
  FOR EACH ROW EXECUTE FUNCTION action_insert_checked();
CREATE FUNCTION action_forward_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.proposal_id <> OLD.proposal_id OR NEW.approval_id <> OLD.approval_id
     OR NOT ((OLD.state = 'unstarted' AND NEW.state = 'attempting')
          OR (OLD.state = 'attempting' AND NEW.state IN ('confirmed','failed','indeterminate')))
     OR (OLD.state = 'unstarted' AND (NEW.attempted_at IS NULL OR NEW.result_at IS NOT NULL))
     OR (OLD.state = 'attempting' AND (NEW.attempted_at <> OLD.attempted_at OR NEW.result_at IS NULL)) THEN
    RAISE EXCEPTION 'action transition is not forward-only';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER action_forward BEFORE UPDATE ON action
  FOR EACH ROW EXECUTE FUNCTION action_forward_only();
GRANT SELECT, INSERT ON action TO argus_runtime;
GRANT UPDATE (state, attempted_at, result_at, evidence) ON action TO argus_runtime;

CREATE TABLE target_hold (
  hold_id text PRIMARY KEY,
  target text NOT NULL,
  reason text NOT NULL,
  placed_by text NOT NULL,
  placed_at timestamptz NOT NULL,
  expires_at timestamptz,
  released_by text,
  released_at timestamptz,
  CHECK ((released_by IS NULL) = (released_at IS NULL))
);
CREATE INDEX target_hold_active ON target_hold(target, placed_at) WHERE released_at IS NULL;
CREATE FUNCTION target_hold_release_once() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.released_at IS NOT NULL OR NEW.released_at IS NULL
     OR NEW.target <> OLD.target OR NEW.reason <> OLD.reason OR NEW.placed_by <> OLD.placed_by
     OR NEW.placed_at <> OLD.placed_at OR NEW.expires_at IS DISTINCT FROM OLD.expires_at THEN
    RAISE EXCEPTION 'target hold can be released only once';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER target_hold_release BEFORE UPDATE ON target_hold
  FOR EACH ROW EXECUTE FUNCTION target_hold_release_once();
GRANT SELECT, INSERT ON target_hold TO argus_runtime;
GRANT UPDATE (released_by, released_at) ON target_hold TO argus_runtime;

-- Only verified outcomes are eligible for future action memory, separated by origin.
CREATE TABLE action_outcome (
  action_id text PRIMARY KEY REFERENCES action(action_id),
  incident_id text NOT NULL REFERENCES incident(id),
  origin text NOT NULL CHECK (origin IN ('lab','drill','production')),
  outcome text NOT NULL CHECK (outcome IN ('recovered_verified','action_failed','indeterminate_escalated')),
  body jsonb NOT NULL,
  recorded_at timestamptz NOT NULL
);
CREATE FUNCTION action_outcome_insert_checked() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.outcome = 'recovered_verified' AND
      (SELECT state FROM action WHERE action_id = NEW.action_id) <> 'confirmed')
     OR (NEW.outcome = 'indeterminate_escalated' AND
         (SELECT state FROM action WHERE action_id = NEW.action_id) <> 'indeterminate') THEN
    RAISE EXCEPTION 'action outcome conflicts with the action ledger';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER action_outcome_insert BEFORE INSERT ON action_outcome
  FOR EACH ROW EXECUTE FUNCTION action_outcome_insert_checked();
GRANT SELECT, INSERT ON action_outcome TO argus_runtime;
