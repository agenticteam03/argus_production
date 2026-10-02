# Argus Brain — start here

> **New developer? Read [`guides/HOW_WE_WORK.md`](guides/HOW_WE_WORK.md) first** (5 minutes): what is planned, how a
> session runs, the language rule, and how commands go from `code.bash` to your terminal and back through
> `output.bash`.

This folder is the **single shared source of truth** for the Argus project: what we are building, where we stand, what
comes next, and how we work. It lives in the same repository as the code, so the code and the knowledge change together
through the same pull requests.

It is written for two readers:
- **developers** (three, all junior): read it to know what to do and why;
- **AI coding agents** (Claude, Codex, Gemini, …): read it at the start of every session and follow
  [`agents/AGENT_PROTOCOL.md`](agents/AGENT_PROTOCOL.md).

## What Argus is (one paragraph)

Argus is a general **SRE incident-diagnosis agent** for servers and containers. When something breaks, it detects the
symptom deterministically, recalls runbooks, investigates with narrow, read-only, audited tools, and either concludes
with a diagnosis or escalates to a human. It is **read-only in this phase**: no write capability is released. It runs
on two real VMs: `vm-095` (agent host) and `vm-166` (primary target + monitoring).

## Reading order (progressive — stop when you have what the task needs)

| # | File | Why |
|---|---|---|
| 1 | this README | orientation, authority, core rules |
| 2 | [`agents/AGENT_PROTOCOL.md`](agents/AGENT_PROTOCOL.md) | how every session runs (agents: mandatory) |
| 3 | [`CURRENT_STATE.md`](CURRENT_STATE.md) | the last **verified** shared state (on `main`) |
| 4 | [`NEXT_STEP.md`](NEXT_STEP.md) → the task file in `tasks/current/` | what to do now |
| 5 | [`tdd/CURRENT_TEST_STATE.md`](tdd/CURRENT_TEST_STATE.md) | the last test results, anything red |
| 6 | the handoff shown by `python brain/tools/brain.py start` | unfinished work from the previous session |
| 7 | `developers/<your-github-handle>.md` | your tools and preferences |
| 8 | the relevant code | — |

Read only when needed: [`architecture/`](architecture/) (the sections your task touches),
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), [`infrastructure/environment.md`](infrastructure/environment.md),
[`journal/`](journal/), and [`guides/`](guides/) when a problem appears.

## Who is authoritative for what

| Information | Authority |
|---|---|
| Architecture | [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) — changed only through an accepted ACR |
| Verified shared state | `CURRENT_STATE.md` **on `main`** |
| Next task | `NEXT_STEP.md` + `tasks/current/<id>.md` |
| Who is working now / unfinished work | `session.json` on the `session` branch (`brain.py status`) |
| What actually runs on the VMs | `/opt/argus-v18/DEPLOYED` on each VM — **the VM wins over the docs** |
| Tests | CI results (truth) · `tdd/CURRENT_TEST_STATE.md` (summary) |
| Policy, inventory, signals | `config/*.yaml` (never copied into the Brain) |
| Runbooks | the separate repo `agenticteam03/runbooks`, at the commit in `config/runbooks.lock` |
| History | `journal/logbook.md` + Git history |

If two files disagree, the higher authority wins and the lower one gets fixed in the same pull request.

## Core rules (the short list — details in `policies/`)

1. **One owner at a time** for the VMs: claim the session lease with `brain.py start`; release it at the end.
2. **Work on a task branch**, never directly on `main`. Only a merged pull request changes the shared state.
3. **Every pull request is reviewed and approved by the next developer** (AI-assisted, [`agents/REVIEW_PROTOCOL.md`](agents/REVIEW_PROTOCOL.md)). Nobody merges their own.
4. **Tests run continuously**: red → green → full suite → CI on every push ([`policies/TDD.md`](policies/TDD.md)).
5. **Commands for the VMs go into `execution/current/code.bash`**, with where, why, what changes, expected output and how to undo ([`policies/CODE_BASH.md`](policies/CODE_BASH.md)).
6. **Never touch the protected objects** (the pre-existing WireGuard deployment, see [`infrastructure/environment.md`](infrastructure/environment.md)); run `nonint-check.sh` before and after every mutating VM step.
7. **No secrets anywhere** in Git, the Brain, `code.bash`, `output.bash` or a chat ([`policies/SECURITY.md`](policies/SECURITY.md)).
8. **The architecture changes only through an ACR** ([`architecture/changes/ACR-TEMPLATE.md`](architecture/changes/ACR-TEMPLATE.md)).
9. **Update the Brain on the task branch together with the code**, so both reach `main` in the same pull request.
10. **AI tools' private memories never hold project state** — only personal preferences. Project facts go here.

## Status ladder (always say which one applies)

`planned → executed → verified → committed → pushed → merged → deployed`

## Stable and mutable parts

- **Stable** (change rarely, by pull request): `architecture/` (only via ACR), `agents/`, `policies/`, `guides/`,
  `infrastructure/`, `IMPLEMENTATION_PLAN.md`.
- **Mutable** (change every session): `CURRENT_STATE.md`, `NEXT_STEP.md`, `tdd/`, `tasks/current/`,
  `execution/current/`, and appends to `journal/logbook.md`.
