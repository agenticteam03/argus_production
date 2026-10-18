# ACR-0020 — Operator terminal: a recorded, human-only shell from the UI

Part of the next-phase proposal ([task](../../tasks/current/NEXT-PHASE-supervised-remediation.md)). Depends on
[ACR-0018](ACR-0018-operator-access-and-audit.md) (operator access and audit), which must be applied and deployed
first. Independent of [ACR-0019](ACR-0019-human-approved-remediation.md): this is the manual repair path, ACR-0019
the Argus-executed one.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-18 |
| Accepted by | pending (team review of the NEXT-PHASE proposal PR) |
| Second approval (safety principle only) | **required**: least privilege (a privileged route and a new container), secrets (an SSH certificate authority) |
| Architecture version | the next free version when applied (after ACR-0018) |
| Task / PR | NEXT-PHASE · PR (this proposal) |

## 1. Detect and explain

When an incident needs a fix that no released action covers, the operator leaves the UI, opens an SSH session from
a laptop (`~/.ssh/config`, a shared `ubuntu` account with sudo), and repairs by hand. Nothing links that session to
the incident, nothing records what was run, and the account is shared, so the audit cannot say who did what.

The team wants the operator in charge to fix any problem from the UI, in a **fully functional terminal**, as
themselves. The threat to manage is **unauthorized external access** to that terminal; authorized operators are
trusted to act, and their actions are **recorded**, not restricted.

## 2. Why the current architecture is insufficient

- §1.2 / §4.6 / §4.7: "No probe offers shell execution", `arbitrary_exec: false`. These rules are about **Argus's**
  tools, and they stay. The architecture has no notion of a **human** shell offered through Argus's UI.
- `IMPLEMENTATION_PLAN.md` §3: "SSH is the operator and transport channel, never an Argus executor." The terminal
  is that operator channel; the architecture must say how it is reached, authenticated and recorded, and that Argus
  never uses it.
- §17.1 layer 14 limits the public edge to the UI contract's routes; a terminal is a long-lived, bidirectional,
  privileged channel and needs its own controls.

## 3. Smallest reasonable change

A new section **§17.4 Operator terminal**:

- **Who:** human principals holding `open_terminal:<host>` (ACR-0018), granted per person and per host, for a time
  window with a reason; never an agent, peer or service principal (enforced by the broker: human principal + MFA
  claim required).
- **Opening:** from the incident page or a maintenance page; the operator states a reason (prefilled with the
  incident id) and passes a **step-up**; the API issues a **single-use ticket** (≤ 60 s, bound to user + host +
  session id); the browser opens a same-origin WebSocket and sends the ticket as its first message (never in a URL).
- **The broker:** a separate container, the only holder of an **SSH certificate authority** key. Per session it signs
  a short-lived certificate (≤ the session's absolute limit) for that person's **own Unix account** (`op-<handle>`)
  on that host, opens SSH, bridges the bytes and records the session. No private key reaches the browser.
- **The hosts:** sshd accepts only certificates of that CA, only for the operator accounts, only from the broker's
  address and the team's admin path; port 22 is not reachable from the Internet; `sudo` I/O logging and `auditd`
  record commands and access to `/opt/argus-v18/secrets/` and the sshd/sudoers configuration.
- **Session limits:** idle 15 min, absolute 4 h (re-authenticate to continue), at most 2 concurrent sessions per
  user; an administrator can kill any session; logout or revocation closes it.
- **The page:** its own origin (or at least its own strict page) with a strict CSP (no inline or third-party
  scripts, Trusted Types); a host banner always visible (vm-095 / vm-166, user, incident, time left); multi-line
  paste asks for confirmation.
- **Exposure:** the ticket route and `/terminal/*` only on the private path (ACR-0018 layer 15); the public edge
  answers 404.
- **Recording and audit:** the full session (input, output, timing) recorded by the broker and shipped **off-host**
  with the sudo and auditd logs; audit events for grant, open, close, kill and refusals; an alert on every session
  start. Recordings may contain secrets an operator printed: access for administrators only, every viewing audited,
  retention defined.
- **Argus's role:** it may offer "Open terminal on <host>" with the incident's context and **"Insert"** a suggested
  command from a runbook (pasted, never executed: no Enter). It never reads or types in a live session, holds no CA
  key or recording, and has **no network path to the broker** (a tested property). After the session, a redacted
  summary of the commands may be attached to the incident as evidence, as data, never as instructions.
- **Leases:** a mutating terminal session on a VM is a mutating step: it needs that VM's lease
  (`policies/PARALLEL_LANES.md`) unless the team defines an on-call exception.
- **Break-glass:** the existing laptop SSH path (or the cloud console) remains the recovery path when the broker or
  the UI is down; its use is announced and recorded in the journal.

**Build or adopt (OD-17, new):** adopt a proven access proxy (Teleport Community Edition is the closest fit) or
build a minimal broker (`xterm.js` + a WebSocket service + `asyncssh` + its own CA). Decided in review.

**Alternatives considered:**
- A: **keep laptop SSH only.** Works, but unlinked to incidents, unrecorded, a shared account.
- B: **a restricted console of allowlisted read verbs.** Safe, but it is not a full terminal and cannot fix arbitrary
  problems; the read verbs already exist for Argus.
- C: **expose ttyd / wetty / gotty behind the edge.** Rejected: no per-user identity, no real authentication, no
  recording.
- D: **give the terminal to Argus.** Rejected: §1.4 rules 1-2 and §4.6; the model never gets a shell.

## 4. Consequences

- **Code:** the ticket route and `/me` permission (api); the broker (adopted or built); the UI terminal panel
  (`xterm.js`), the host banner, the step-up and reason dialog.
- **Tests:** no `open_terminal` → no control and 403; a replayed ticket, a ticket in a URL, a forged Origin are
  refused; idle and absolute timeouts close the session; the recording and sudo log are found off-host; Argus's
  containers cannot reach the broker (network test); the public edge answers 404 for `/terminal/*`.
- **Deployment:** the broker container (vm-095 first; its own host later), operator Unix accounts and sshd/sudoers/
  auditd configuration on both VMs (managed objects in `infrastructure/environment.md`), the off-host recording
  store.
- **Brain:** `policies/SECURITY.md` (a new principle "Operator terminal: humans only, MFA, private access, recorded";
  the SSH CA and recordings in the secrets table); `policies/NETWORK.md` (broker → sshd; port 22 closed to the
  Internet); `AGENT_PROTOCOL.md` (the agent never opens or types in a terminal); `PARALLEL_LANES.md` (leases);
  `guides/TROUBLESHOOTING.md` (the terminal's own incident response: kill sessions, revoke the CA, close the route).
- **Risk:** the broker is a high-value target (a compromise gives shells on both VMs): isolation, minimal
  dependencies, updates, monitoring, and moving it off vm-095 later.
- **How to reverse it:** close `/terminal/*` at the edge (one block), revoke the CA (KRL on both hosts), stop the
  broker; laptop SSH remains.
- **Safety principles touched:** yes: least privilege, secrets. Argus's own read-only principle does **not** change.
  Second approval required.

## 5. Decision

Proposed. To be accepted or changed in the NEXT-PHASE proposal PR review, together with OD-17 (build or adopt).

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§1.2 note, §3 the broker, §17.1 layer reference, new §17.4, §18, §25 OD-17,
      changelog), version bumped
- [ ] `policies/SECURITY.md`, `NETWORK.md`, `AGENT_PROTOCOL.md`, `PARALLEL_LANES.md`,
      `infrastructure/environment.md`, `guides/TROUBLESHOOTING.md`
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
