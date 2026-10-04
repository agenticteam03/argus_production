# START HERE — joining the Argus project

**For the developer:** put this file in an empty folder (for example `C:\repos\argus`), open your AI agent (Claude
Code: `claude`) in that folder and say: **"Read START_HERE.md and follow it."** That's all. The agent does the rest
with you, step by step. This file contains no secrets, so it can be shared by chat or email.

**For the AI agent:** you are onboarding a new developer of the Argus project. Follow the parts below **in order**.
Before each step, say in one or two sentences what it does and why. Run the commands yourself when you can; ask the
developer only for what needs them (a browser login, a private file, a choice). After each part, say clearly whether
it passed. Never ask for, print or store a secret. If a step fails, explain the error in plain language and fix it
with the developer before moving on.

---

## Part 1 — Language and identity

1. Ask which language they prefer for the conversation (for example English or Spanish) and use it from now on.
   Everything written into the repository (code, comments, commits, pull requests, Brain files) stays in English.
2. Ask their GitHub handle. It must be one of: `juanbetancurm`, `conantkd`, `juanes6554`.

## Part 2 — Tools on the laptop (once per machine)

Check each tool; for a missing one, give the install command, wait until it is installed, then check again.

| Tool | Check | Install (Windows) | Needed for |
|---|---|---|---|
| Git | `git --version` | `winget install Git.Git` | everything |
| Python 3.12+ | `python --version` | `winget install Python.Python.3.12` | tests, tools |
| GitHub CLI | `gh --version` | `winget install GitHub.cli` | the private repository, pull requests |
| Docker Desktop (optional) | `docker version` | `winget install Docker.DockerDesktop` | the Postgres tests only |

After installing something, a new terminal (or a new agent session) may be needed so it is found.

Then GitHub: run `gh auth status`. If it is not logged in, ask the developer to run **`! gh auth login`** in this
session (GitHub.com → HTTPS → "Login with a web browser"); it opens the browser once. Being an owner of the
organization gives permission; this login gives *this laptop* access.

## Part 3 — Get the code

1. In this folder: `gh repo clone agenticteam03/argus_production` (it creates the subfolder `argus_production`).
2. From now on, work **inside `argus_production`**. In future sessions, open the agent directly in that folder; it
   reads `CLAUDE.md` / `AGENTS.md` automatically, which sends it to `brain/README.md`.

## Part 4 — Set up the project (inside `argus_production`)

Run, and explain briefly what each line does:

```powershell
python -m venv .venv                                   # a private Python environment for this project
.\.venv\Scripts\python -m pip install -e ".[test,dev]" # Argus + test tools + the commit checks
.\.venv\Scripts\pre-commit install                     # checks on every commit (no secrets) and push (never to main)
git config argus.developer <their-github-handle>       # who you are, for the VM session lease
git config core.autocrlf input                         # keep Linux line endings (files go to Linux VMs)
.\.venv\Scripts\python -m pytest -q                    # all tests must pass (Postgres tests are skipped without Docker)
python brain\tools\brain.py lint                       # the shared Brain is consistent
```

Part 4 passes when the tests end with only dots and `s` (skipped), and lint prints `lint: clean`.

## Part 5 — Access to the two VMs (only needed for tasks that run commands on the VMs)

Test: `ssh -o BatchMode=yes -o ConnectTimeout=10 argus-vm095 hostname` (expected `vm-appsvnic`) and the same with
`argus-vm166` (expected `agent-test-vnic`).

If it fails:
- the developer's `~/.ssh/config` needs the two entries shown in `brain/infrastructure/ssh-config.example`;
- **the developer types the two addresses and the key path into their own `~/.ssh/config` themselves** — they come
  privately from `juanbetancurm` (or the developer already has their own access to the VMs). Addresses and keys are
  never written into the repository and never pasted into the chat;
- then test again. If it still fails, stop here; the rest works without VM access.

The shared Argus password (for the agent's CLI and Swagger) is only needed later; it is typed at hidden prompts,
never written anywhere.

## Part 6 — How we work

Read `brain/guides/HOW_WE_WORK.md` and explain it to the developer in their language, in about five minutes: what is
planned, how a session runs, `code.bash` → their terminal → `output.bash`, and the four rules never to break. Then
read `brain/README.md` and `brain/agents/AGENT_PROTOCOL.md` yourself and follow them from now on.

## Part 7 — First pull request: your developer file

A small, safe first contribution that teaches the workflow:

1. `git checkout -b task/onboard-<handle> main`
2. Copy `brain/developers/TEMPLATE.md` to `brain/developers/<handle>.md` and fill it in with the developer (role,
   agent, laptop, VM access yes/no, conversation language, preferences — no secrets).
3. Show the developer the commit message before committing; commit; `git push -u origin task/onboard-<handle>`.
4. Open the pull request (`gh pr create`), with another developer as reviewer. Nobody merges their own pull request.

## Part 8 — Start working

Run `python brain\tools\brain.py status`. If a teammate's pull request is waiting for review, that comes first:
follow `brain/agents/REVIEW_PROTOCOL.md` with the developer. Otherwise continue with `brain/NEXT_STEP.md`.

**Done.** Tell the developer: for every future session, open the agent in `argus_production` and say
"Hi, I'm <handle>" — the agent will run `brain.py start` and take it from there.
