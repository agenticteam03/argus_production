# How we work — read this first (developers)

Five minutes. Everything else in the Brain is detail you or your AI agent read when needed.

## 1. What we are doing

- **Argus** is our SRE incident-diagnosis agent. It already runs on two VMs: `vm-095` (the agent) and `vm-166` (the
  main target). It is read-only: it diagnoses, it never changes anything.
- **This repository** holds the code **and** the project's shared memory, the **Brain** (`brain/`): where we stand,
  what comes next, and the rules. Your AI agent reads the Brain at the start of every session, so you do not need
  to explain the project to it.
- **What is planned, in order:**
  1. finish the setup (deploy keys so the VMs pull the code from GitHub);
  2. team decision **D-001** (how the two VMs talk) — see [`../OPEN_PROBLEMS.md`](../OPEN_PROBLEMS.md);
  3. the first real task, **T-0013**: the investigation workflow in LangGraph, able to resume after a crash;
  4. then the plan's remaining phases: [`../IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md).
  Where we are right now: [`../CURRENT_STATE.md`](../CURRENT_STATE.md) and [`../NEXT_STEP.md`](../NEXT_STEP.md).

## 2. A session, from start to end

1. Open your AI agent in this repository and tell it: *"Read brain/README.md and follow the protocol. I am
   `<your-github-handle>`."*
2. It runs `python brain/tools/brain.py start`: it updates your copy and reserves the VMs for you for 60 minutes
   (renewed automatically while you work). If someone else holds them, it tells you — then you do code-only work or wait.
3. If a teammate's pull request is waiting, **you review it first**, with the agent's help, and merge it.
4. You work on the next task in small steps (below).
5. At the end: the agent releases the VMs (`brain.py release`), or leaves a handoff note if the task is unfinished.

## 3. The language

Talk to the agent in the language you prefer — **Spanish is fine**. The agent will ask you at the start. But
everything written into the repository is **English**: code, comments, commit messages, pull requests, `code.bash`
and the Brain.

## 4. How commands reach the VMs: `code.bash` → your terminal → `output.bash`

The agent never logs into the VMs. **You** run the commands, and the agent checks the result.

1. **The agent writes** the next step into `brain/execution/current/code.bash`. Every block starts with a label that
   says exactly where it runs:
   - `[LAPTOP · PowerShell]` → paste it into a PowerShell window on your laptop;
   - `[VM vm-095 · bash]` → first connect with `ssh argus-vm095`, then paste it there;
   - `[VM vm-166 · bash]` → first connect with `ssh argus-vm166`, then paste it there.
   Each block also says what it changes (READ-ONLY or MUTATES), how to undo it, and the **expected** result.
2. **You copy** one block at a time, paste it into the right terminal, and press Enter. A block meant for a VM pasted
   into PowerShell fails (for example *"sudo is not recognized"*) — check the label first.
3. **You copy everything the terminal printed** — commands and output — into `brain/execution/current/output.bash`
   (create the file the first time; **replace** its content at each new step). This file never goes to GitHub.
4. **You tell the agent:** *"output.bash updated"*.
5. **The agent checks** the result and gives you the next step.

Never paste a password, token or key into `output.bash` or into the chat. Commands that need one ask for it with a
hidden prompt.

## 5. How the agent reads `output.bash` (and why)

Outputs can be long, and reading all of them costs time and tokens. Every block ends with a clear **verdict line**
(for example `NO INTERFERENCE`, `TUNNEL TARGET MATCHES`, `47 passed`, `STOP: …`), and the expected lines are written
next to each command. The agent first **searches** the file for those lines and for error words (`error`, `failed`,
`denied`, `STOP`, `Traceback`); it reads a section in full only when something is missing or unexpected. So: paste
everything, do not trim it — the agent decides what to read.

## 6. When something goes wrong

Tell the agent what you saw. It follows [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md): it explains what the error means,
checks one thing at a time, and decides with you what to do. It stops and asks you to involve a teammate if anything
could lose data, expose a secret, or disturb the other Argus deployment on the VMs.

## 7. The four rules you must never break

1. Never touch the other deployment on the VMs (`/opt/argus`, `/opt/argus-lab`, `wg0`, `labmvp`).
2. Never put a secret in any file, commit or chat.
3. Never push to `main`. Merge your own pull request only when it meets the self-merge rule (required checks green
   on its last push, no protected path: `../agents/REVIEW_PROTOCOL.md`); otherwise the next developer reviews it.
4. Never reboot a VM.
