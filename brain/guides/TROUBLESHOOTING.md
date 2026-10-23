# Troubleshooting — what to do when something goes wrong

## The method (the agent follows it every time)

1. **Restate.** What were we trying to do, and what actually happened? Quote the exact output line.
2. **Classify** the problem, and say why:

   ```text
   Did the command run in the right place (laptop vs vm-095 vs vm-166)?  ── no ──▶ WRONG PLACE
        │ yes
   Is it the network, SSH, Docker not running, credentials, disk?        ── yes ─▶ ENVIRONMENT
        │ no
   A typo, the wrong directory, a skipped step?                          ── yes ─▶ USAGE
        │ no
   Does the code do something different from its test / the spec?        ── yes ─▶ IMPLEMENTATION BUG
        │ no
   Does the test assert the wrong thing?                                 ── yes ─▶ TEST BUG
        │ no
   Is the specification itself wrong or incomplete?                      ── yes ─▶ ARCHITECTURE ISSUE (→ ACR)
        │ no
   UNKNOWN → gather more evidence
   ```
3. **Investigate** with **one read-only diagnostic command at a time**; explain what each one checks and what its
   answer means.
4. **Explain the error** in plain language, including what the message literally means.
5. **Decide together:** retry, fix the code, fix the test, open an ACR, or stop and ask the team (stop conditions in
   `agents/AGENT_PROTOCOL.md` §6).

Record the lesson: the journal entry gets a `Learned:` line; a problem seen twice goes into the catalog below.

## Catalog — problems already seen in this project

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `bash: $'\r': command not found`, or a script fails strangely on the VM | the file has **Windows line endings (CRLF)**; Python `Path.write_text` on Windows writes CRLF | convert to LF; write bytes with `\n`; the test `test_deployable_files_have_unix_line_endings` catches it |
| 2 | a command on the VM asks for the Argus password again although you exported it | **`sudo` drops environment variables** | `sudo --preserve-env=ARGUS_PASSWORD docker exec -e ARGUS_PASSWORD …` |
| 3 | `docker compose up --build` prints "CACHED" / "Running" and the change is not visible | the build context did not change on the VM (stale code), or compose did not recreate the container | check `/opt/argus-v18/DEPLOYED` is the expected commit; `docker compose … up -d --build --force-recreate <service>` |
| 4 | `client_loop: send disconnect: Connection reset` mid-task | the SSH session dropped (network) | reconnect; re-run the step (blocks are safe to re-run); check whether the last command completed |
| 5 | `sudo : The term 'sudo' is not recognized` in PowerShell | a **VM command run on the laptop** | open the VM shell first: `ssh argus-vm095`; check the block's `[… · bash]` label |
| 6 | `git clone` / `git ls-remote` hangs or asks for a username/password | Git has no GitHub credentials | `gh auth login`, then `gh auth status` |
| 7 | Postgres tests skipped, or `docker: error during connect` | Docker Desktop is not running, or `ARGUS_TEST_PG_OWNER_DSN` is not set | start Docker Desktop; follow `policies/TDD.md` |
| 8 | a check says **healthy** while the exporter is down | metrics were stale: a range function kept answering from old samples | fixed: the `_scrape_up` freshness gate makes it **undiagnosable**; "missing is unknown, never healthy" |
| 9 | an incident is "diagnosed" with an **empty diagnosis** | the model sent `diagnosis: ""` | fixed: `conclude` requires ≥ 20 characters (schema `minLength` + harness check) |
| 10 | a container keeps an **anonymous volume** after switching to `tmpfs` | compose keeps old anonymous volumes attached on recreate | remove it only after proving its sole user is our container; `nonint-check` shows it |
| 11 | the model answers HTTP 400 when tools are sent | this model does not accept function tools on `/v1/chat/completions` | use the Responses API (`ARGUS_LLM_API=responses`, the default); 4xx is never retried |
| 12 | `required variable ARGUS_VM166_PRIVATE_IP is missing a value` | compose for the core was run without the VM-local address file | add `--env-file /opt/argus-v18/hosts.env`; check the file exists |
| 13 | after a restart, an OOM crash looks like a normal exit | Docker resets `ExitCode`/`OOMKilled` once the container runs again | fixed: the exporter takes the last exit from `die`/`oom` events in the 10-minute window |
| 14 | `HTTP 422 ... Deploy keys are disabled for this repository` | the organization setting "Deploy keys" is off (an empty `gh repo deploy-key list` does NOT prove they are allowed) | an org owner allows them: Organization settings → Member privileges → Deploy keys |
| 15 | `HTTP 403 Upgrade to GitHub Pro or make this repository public` on branch protection | free organization plan: no branch protection on private repos | the soft review rules (`brain.py verify-main`, pre-push hook) — see `agents/REVIEW_PROTOCOL.md` |
| 17 | a crash-looping container is reported UNSUPPORTED ("no class matched", `restarts_10m=1`) although Docker shows 3+ restarts | Prometheus samples every 15 s and `restarts_10m` is computed from its samples, so it trails Docker's own counter | wait on Prometheus, not Docker: poll `restarts_10m` on the target host's Prometheus until ≥ 3 (T-0013 step 5, S5.6) |
| 16 | `DEPLOY STOP: NOT YOUR SESSION` | `/opt/argus-v18/SESSION` names someone else, or the marker line was not pasted | `brain.py start`, then paste its VM-marker line on the VM |
| 18 | a pasted block **hangs with no output** at `db-migrate.sh`, `argus diagnose` or another `docker exec -i` command | `docker exec -i` forwards the terminal's stdin, so it waits on (or swallows) the rest of the pasted block; a `\| tail` hides that it is waiting | Ctrl+C (check `pg_stat_activity`: nothing half-applied); run it with `< /dev/null` and without `\| tail` (DEPLOY-MAIN D.2) |
| 19 | a `--check` on a lab service says DIAGNOSED instead of HEALTHY | the lab is not in its baseline state (e.g. `argus-lab-cache` left stopped after a scenario) — Argus is right | `sudo bash /opt/argus-v18/app/ops/deploy.sh status` (it ends with `LAB BASELINE OK` or names the stopped/unhealthy lab containers); restore the baseline, then re-check (DEPLOY-MAIN D.3b) |
| 20 | `argus: command not found` on a VM, and `apt` suggests installing `argus-server` | the Argus CLI is not installed on the host: it lives in the `argus-v18-agent` container (`argus-server` is an unrelated Debian package) | `sudo docker exec argus-v18-agent argus ... < /dev/null`; never install `argus-server` (PHASE-16 enrolment, 2026-10-23) |

## First diagnostic commands

| Question | Command (read-only) |
|---|---|
| Which commit runs on this VM? | `cat /opt/argus-v18/DEPLOYED` |
| Are our containers up? | `sudo docker ps --filter name=argus- --format '{{.Names}} {{.Status}}'` |
| Why does a container restart? | `sudo docker logs --tail 50 <name>` |
| Is the agent healthy? | `curl -s http://127.0.0.1:18000/healthz` (on vm-095) |
| Did we disturb anything? | `sudo bash /opt/argus-v18/app/ops/nonint-check.sh after` |
| Is the tunnel up? | `sudo docker logs --tail 5 argus-v18-tunnel` (on vm-095) |
| Is the database fine? | `sudo docker exec -it argus-v18-agent argus db check` |
