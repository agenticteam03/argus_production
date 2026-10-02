# Policy — commands for developers (`code.bash` / `output.bash`)

Every command a developer must run goes into **`brain/execution/current/code.bash`**. The developer pastes what the
terminal printed into **`brain/execution/current/output.bash`** (gitignored, never committed) and tells the agent
"output.bash updated". The agent validates it against the expected lines. The developer-facing explanation is
[`../guides/HOW_WE_WORK.md`](../guides/HOW_WE_WORK.md) §4–§5.

## Reading `output.bash` economically (agents)

Do not read the whole file by default. First **search** it: the step's verdict lines and `Expected:` markers, and
error words (`error`, `fail`, `denied`, `refused`, `STOP`, `MISMATCH`, `Traceback`, `exit code`, `not recognized`).
If every verdict is present and no error word appears, the step passed — say so and move on. Read a section in full
only when a verdict is missing or an error word appears. To make this possible, **every block ends with a printed
verdict line** that is unique and greppable (e.g. `NO INTERFERENCE`, `TUNNEL TARGET MATCHES`, `47 passed`), or with
an explicit `&& echo "<STEP> OK" || echo "<STEP> STOP: <reason>"`.

## Block format

```bash
# =====================================================================================
# STEP T-0013.4 — Rebuild the agent with the LangGraph runner                [~3 min]
# Goal / Why: one or two lines.
# MUTATES: rebuilds and restarts argus-v18-agent only.   Undo: <exact rollback command>
# =====================================================================================

# --- 4.1 [VM vm-095 · bash] (ssh argus-vm095) Check the session marker and take the "before" snapshot ---
grep -q "holder=<you>" /opt/argus-v18/SESSION || { echo "NOT YOUR SESSION"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before

# --- 4.2 [VM vm-095 · bash] Rebuild -----------------------------------------------------------------------
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env \
  -f compose.core.yml up -d --build --no-deps argus-v18-agent && cd ~
# Expected: "Container argus-v18-agent Started"

# --- 4.3 [VM vm-095 · bash] Prove non-interference ----------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after          # expected: NO INTERFERENCE
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
```

## Rules

1. **Label every block** with where it runs: `[LAPTOP · PowerShell]`, `[VM vm-095 · bash]`, `[VM vm-166 · bash]`,
   and how to get there (`ssh argus-vm095`). Most mistakes so far were a command run in the wrong place.
2. **Say READ-ONLY or MUTATES**, and for every mutating block the exact **undo** command.
3. **Write the expected result** next to each command, before it is run.
4. **Mutating blocks** start with the session-marker check and `nonint-check.sh before`, and end with
   `nonint-check.sh after` → `NO INTERFERENCE`.
5. **Safe to re-run:** guard creations (`test -f … ||`, `id user ||`), never blindly delete.
6. **No secrets** in commands or outputs; hidden prompts only.
7. **Deployment** is `ops/deploy.sh <commit-or-branch>` on each VM (the VMs pull from Git); the old laptop tarball
   (`scp`) is only the fallback when GitHub is unreachable.
8. **Compose for the core on vm-095** always passes `--env-file /opt/argus-v18/hosts.env`.
9. Prefer PowerShell 5.1-compatible syntax on the laptop (no `&&`); LF line endings for anything sent to the VMs.

## After the step

The agent archives it as `brain/execution/history/<task>/step-NN/code.bash` + `evidence.md` (the key output lines,
sanitized: no IPs, no secrets), clears `execution/current/`, and updates the Brain on the task branch.
