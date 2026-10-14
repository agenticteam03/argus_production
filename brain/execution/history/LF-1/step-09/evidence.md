# LF-1 step 09 - OTLP accepted; concurrent core change invalidates trial

Status: executed, interrupted automatically; no full capacity pass. Langfuse ready in 256 seconds. One OTLP batch (10 traces / 20 observations) was accepted. Before the next batch, the monitor detected changed Argus service state and aborted. The requested 60-trace read verification was not reached.

Argus agent/worker StartedAt changed to approximately 05:49:43 UTC; both are running with OOM false and restart counts zero after cleanup. Two non-200 health samples were recorded during startup. The trial does not deploy/recreate core services, but the cause of these concurrent recreations is not independently attributed. Do not attribute the interruption to Langfuse capacity or claim non-disruption.

Read-only follow-up: DEPLOYED records main / 2d3b365 (previous 46ba3a3); the same authorized shared SESSION marker remains. No trial containers or volumes remain; /healthz returns 200; NO INTERFERENCE passed. Minimum available RAM: 2442 MiB.

Details: [sanitized measurements](measurements.json); [guarded invocation](code.bash). Next: obtain a stable test window with no concurrent deployment/recreation, repeat the fresh baseline, and rerun all ingestion/read acceptance checks. Preserve the other task lease.
