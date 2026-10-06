# Continue on another laptop (already set up once)

For a laptop that already has a clone of `argus_production`, a `.venv` and the SSH keys for the VMs, but has not been
used for a while. A brand-new laptop follows [`../../START_HERE.md`](../../START_HERE.md) instead. All commands are
PowerShell, run **inside the `argus_production` folder**. Every line says what to expect; stop at the first surprise
and tell your agent.

## 1. Before leaving the old laptop

- Everything committed and pushed (`git status` clean, `git log origin/<branch>..` empty), and the VM lease
  released (`python brain\tools\brain.py status` → `Lease: released`).
- `brain/execution/current/output.bash` never travels (it is gitignored): paste anything still needed into the chat
  or the evidence first.

## 2. Bring the clone up to date

```powershell
git status                          # must be clean. If not: STOP and ask your agent (it may be unpushed work)
git remote -v                       # origin = git@github.com:agenticteam03/argus_production.git (or https://github.com/agenticteam03/argus_production.git)
git fetch --prune origin            # get every branch and the session lease
git switch main
git pull --ff-only                  # must fast-forward; if it refuses, ask your agent
git log --oneline -3                # the newest merge must match main on GitHub
```

If `origin` is missing or wrong:
`git remote set-url origin https://github.com/agenticteam03/argus_production.git` (or `git remote add origin …`).

## 3. Dependencies, checks and identity

```powershell
.\.venv\Scripts\python -m pip install -e ".[test,dev]"   # IMPORTANT: new dependencies (LangGraph since T-0013)
.\.venv\Scripts\pre-commit install                       # commit checks (secrets) + push check (never to main)
git config argus.developer                               # must print your GitHub handle
git config user.name; git config user.email              # who your commits are from
gh auth status                                           # logged in to github.com? If not: gh auth login
.\.venv\Scripts\python -m pytest -q                      # expected: all passed, 5 skipped (Postgres needs Docker)
.\.venv\Scripts\python brain\tools\brain.py lint         # expected: lint: clean
```

If `.venv` is missing or broken: `python -m venv .venv`, then the `pip install` line again.
`No module named 'langgraph'` in the tests means the `pip install` line was skipped.

## 4. VM access (only for tasks with VM steps)

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 argus-vm095 hostname    # expected: vm-appsvnic
ssh -o BatchMode=yes -o ConnectTimeout=10 argus-vm166 hostname    # expected: agent-test-vnic
```

A failure here: check `~/.ssh/config` against [`../infrastructure/ssh-config.example`](../infrastructure/ssh-config.example)
and that the key file it names exists. Never paste a key or an address into a chat.

## 5. Start the session

```powershell
python brain\tools\brain.py status     # who holds the VMs, open pull requests, the handoff note
```

Then open your AI agent in this folder and say **"continue the project"**. It follows
[`../agents/AGENT_PROTOCOL.md`](../agents/AGENT_PROTOCOL.md): reviews first, then [`../NEXT_STEP.md`](../NEXT_STEP.md).
It claims the VM lease (`brain.py start`) only when a task needs the VMs.

## 6. If the laptop restarts in the middle of work

Nothing is lost if you commit and push at every step. After the restart: `git status` (unpushed work?), then
`python brain\tools\brain.py status`. The VM lease expires by itself; if a VM step was interrupted, the first VM
block is the state probe (`sudo bash /opt/argus-v18/app/ops/deploy.sh status` → commit, ref, `LAB BASELINE`) before
anything else.
