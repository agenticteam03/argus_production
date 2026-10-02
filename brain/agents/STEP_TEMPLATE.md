# Step template

Every step the agent proposes to a developer uses this shape. It is short on purpose: the developer must understand
**what**, **why**, **where** and **how to tell success from failure** before running anything.

```text
STEP <task>.<n> — <title>
Goal:        what we are trying to achieve (1–2 sentences, plain language)
Why:         why this step is needed now, and which phase / acceptance criterion it serves
Where:       [LAPTOP · PowerShell] / [VM vm-095 · bash] / [VM vm-166 · bash] — and how to get there (ssh argus-vm095)
Changes:     READ-ONLY, or MUTATES (what exactly) — and how to undo it
Command:     the exact commands (also written to brain/execution/current/code.bash)
Expected:    what success looks like (the key lines), and roughly how long it takes
If it fails: the 2–3 most likely causes, and the first diagnostic command for each
```

## Example

```text
STEP T-0013.4 — Rebuild the agent with the LangGraph runner
Goal:        run the new LangGraph-based workflow on vm-095 instead of the plain-Python runner.
Why:         Phase 9 needs the v1.8 skeleton with a checkpointer so an investigation survives a crash.
Where:       [VM vm-095 · bash] — ssh argus-vm095
Changes:     MUTATES: rebuilds and restarts the container argus-v18-agent only.
             Undo: ops/deploy.sh <previous commit> and rebuild the agent again.
Command:     cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env \
               -f compose.core.yml up -d --build --no-deps argus-v18-agent
Expected:    "Container argus-v18-agent Started"; then `docker ps` shows it Up; ~2 minutes.
If it fails: 1. "required variable ARGUS_VM166_PRIVATE_IP is missing" → hosts.env missing: `ls -l /opt/argus-v18/hosts.env`
             2. build error → `sudo docker compose ... build argus-v18-agent 2>&1 | tail -30`
             3. container restarts → `sudo docker logs --tail 50 argus-v18-agent`
```

Rules:
- One step = one purpose. Split a step that both reads and mutates.
- `Expected` is written **before** the developer runs the step (for infrastructure steps it replaces the red test).
- Mutating VM steps are wrapped by `nonint-check.sh before` / `after` (see `policies/CODE_BASH.md`).
