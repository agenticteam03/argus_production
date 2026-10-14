# LF-3 local implementation

Status: work in progress on an isolated local branch. The Argus worker emits bounded metadata-only OTLP spans; the
Agent page shows recent run activity and trace correlation IDs from the existing read-only API. A private six-service
Langfuse Compose stack and VM acceptance procedure are prepared. No PR, push or VM execution is part of this session.

### Test state

Focused Langfuse exporter and graph-runner tests passed after the model-span addition.
The model-span test was red before implementation. The Agent summary unit test, frontend lint of new files, and
production build passed. The browser-rendered desktop demo was inspected from a local offline preview. Full backend
verification remains pending because automatic approval review exhausted its usage limit while authorizing execution
in the isolated worktree. VM ingestion and capacity validation await a lease.

### Next step

Complete full local verification. When the VM leases are available, perform the private stack and canary
sequence in `deploy/langfuse/README.md`, using the Brain code.bash protocol and preserving sanitized evidence.
