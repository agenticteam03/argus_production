-- 002: LangGraph checkpoint tables (T-0013). The graph runner saves its state here after every node, so an
-- investigation interrupted by a crash or restart resumes after the last completed node.
--
-- This is LangGraph's own schema (langgraph-checkpoint-postgres 3.1, BasePostgresSaver.MIGRATIONS 0-9), created by the
-- owner because the runtime role has no DDL. Differences from the library's setup(): the three indexes are created
-- non-concurrently (ops/db-migrate.sh runs each file in one transaction; the tables are empty here), and the
-- covered library migrations are recorded in checkpoint_migrations so the library never tries to apply them.
-- A library upgrade that adds a migration makes tests/test_graph_runner.py fail: then write 003, never edit this file.

CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id);
CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id);

INSERT INTO checkpoint_migrations (v) VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9) ON CONFLICT DO NOTHING;

-- The runtime role reads and writes checkpoints but cannot delete them (the "no DELETE anywhere" guarantee holds;
-- LangGraph deletes only in delete_thread, which Argus never calls).
GRANT SELECT, INSERT, UPDATE ON checkpoints, checkpoint_blobs, checkpoint_writes TO argus_runtime;
GRANT SELECT ON checkpoint_migrations TO argus_runtime;
