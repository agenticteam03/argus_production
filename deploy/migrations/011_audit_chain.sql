-- 011: the audit hash chain (ACR-0018 §17.1 layer 13, phase 16 step 1).
-- Every audit row written from now on carries prev_hash (the previous chained row's hash) and its own hash
-- (argus/domain/audit_chain.py). The store writes one row at a time under a transaction-level advisory lock, so
-- concurrent writers (api, worker, scheduler) never fork the chain. Rows written before this migration keep a NULL
-- hash: `argus audit verify` counts them and chains everything after. Adding the columns rewrites the table; it is not
-- an UPDATE, so the insert-only trigger of 001 does not fire, and it stays in force for every role.

ALTER TABLE audit ADD COLUMN seq bigserial;
ALTER TABLE audit ADD COLUMN prev_hash text CHECK (prev_hash IS NULL OR prev_hash ~ '^[0-9a-f]{64}$');
ALTER TABLE audit ADD COLUMN hash text CHECK (hash IS NULL OR hash ~ '^[0-9a-f]{64}$');
CREATE INDEX audit_seq ON audit (seq);

GRANT USAGE ON SEQUENCE audit_seq_seq TO argus_runtime;
