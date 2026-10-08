-- 003: the worker's claim is a lease (T-0014, ARCHITECTURE §6.2). A worker claims a queued incident until
-- claimed_until and renews it while the run lasts; only runs whose lease expired (their worker died) go back to the
-- queue, so several workers can run safely. The runtime role already has UPDATE on incident (001).

ALTER TABLE incident ADD COLUMN claimed_by text;
ALTER TABLE incident ADD COLUMN claimed_until timestamptz;
CREATE INDEX incident_claim ON incident (status, claimed_until);
