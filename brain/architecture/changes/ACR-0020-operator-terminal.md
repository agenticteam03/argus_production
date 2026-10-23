# ACR-0020 — Operator terminal: a recorded, human-only shell from the UI

Part of the next-phase proposal ([task](../../tasks/current/NEXT-PHASE-supervised-remediation.md)). Depends on
[ACR-0018](ACR-0018-operator-access-and-audit.md) (operator access and audit), which must be applied and deployed
first. Independent of [ACR-0019](ACR-0019-human-approved-remediation.md): this is the manual repair path, ACR-0019
the Argus-executed one.

| Field | Value |
|---|---|
| Status | `accepted` (21A applied; privileged stages blocked by the phase-16 exit proof) |
| Proposed by | juanbetancurm (+ agent) · 2026-10-18 |
| Accepted by | conantkd · 2026-10-23 |
| Second approval (safety principle only) | **required**: least privilege (a privileged route and a new container), secrets (an SSH certificate authority) |
| Architecture version | 1.8.31 (21A contracts and broker core) |
| Task / PR | [PHASE-21](../../tasks/current/PHASE-21-operator-terminal.md) · PR pending |

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
- **Argus's role:**
  - It may offer "Open terminal on <host>" with the incident's context, and **"Insert"** a command (pasted, never
    executed: no Enter).
  - Insert offers only commands that an **action card** (ACR-0019 §3.4) or a runbook lists for that service, and only
    when the **service card** permits the action, with the incident's evidence cited next to it.
  - It never reads or types in a live session, holds no CA key or recording, and has **no network path to the
    broker** (a tested property).
  - After the session, a redacted summary of the commands may be attached to the incident as evidence (data, never
    instructions), and a follow-up check runs (ACR-0022 §3.2). The operator's "I did it manually" goes into the memory
    of actions (ACR-0019 §3.12).
- **Two kinds of manual work:**
  - **Through Argus** (Insert, "Convert to proposal"): Argus offers only what the service and action cards allow,
    with cited evidence.
  - **The terminal itself:** a full shell for the authorized operator, who is responsible for what they type. The
    controls are access (ACR-0018) and recording, not command restrictions.
- **Leases:** a mutating terminal session on a VM is a mutating step: it needs that VM's lease
  (`policies/PARALLEL_LANES.md`) unless the team defines an on-call exception.
- **Break-glass:** the existing laptop SSH path (or the cloud console) remains the recovery path when the broker or
  the UI is down; its use is announced and recorded in the journal.

**Build or adopt (OD-17, decided):** build a narrow Argus terminal broker for the lab (`xterm.js` + a WebSocket
service + `asyncssh` + its own CA), rather than adopt Teleport Community Edition.

The broker reuses the identity, session revocation, WebAuthn step-up, per-host permission and private path of
ACR-0018. It has no login page or role database of its own. The API creates a single-use launch ticket after policy
checks; the broker consumes that ticket, maps the already-authenticated principal to one fixed `op-<handle>` account,
opens SSH and records the byte stream. This keeps one source of identity and makes the incident id, reason and lease
part of the session from its first event.

Teleport already provides an SSH CA, [browser terminals](https://goteleport.com/docs/connect-your-client/teleport-clients/web-ui/),
RBAC, audit events and [session recordings](https://goteleport.com/docs/reference/architecture/session-recording/).
It is not the smallest fit here because it adds a second identity and authorization plane and a separate Web UI, while Argus still
needs custom work to bind its step-up token, incident, reason and VM lease to the Teleport session. Its Community
Edition distribution also has use restrictions from version 16 onward; compiling the source uses AGPLv3
([upstream licensing notice](https://github.com/gravitational/teleport/discussions/39158)). The team
would have to settle that licensing question before treating it as a project dependency. Revisit Teleport when the
number of hosts or operators makes maintaining a small broker less safe than integrating a dedicated access plane.

The custom broker is deliberately not a general access product:
- one WebSocket protocol, one SSH session type and the two declared hosts; no arbitrary destination supplied by the
  browser;
- no password authentication, long-lived user key, shell command API, file transfer, port forwarding or agent
  forwarding;
- the CA key and recording credential exist only in the broker; the API and worker cannot read them;
- synchronous recording: if the broker cannot persist the stream and final manifest, the session is closed;
- every mutable boundary (hosts, principal-to-account mapping, limits and recording destination) is configuration
  reviewed in Git or an ACR-0018 protected deployment object, never browser input.

**Implementation order:** 21A may land offline after this decision. Steps 21B–21E wait for ACR-0018's phase-16 exit
proof because they add privileged routes, credentials, connectivity or deployment.
1. **21A — contracts and broker core, offline:** ticket claims, session state machine, fixed target/account mapping,
   recording manifest and lifecycle audit events; fake SSH and object-store adapters; no route and no deployment.
2. **21B — privileged API:** `open_terminal:<host>`, reason and incident validation, step-up bound to the terminal
   ticket, single-use consumption, kill/list routes and authorization matrix under `/api/v1/ops/terminal/`.
3. **21C — browser terminal:** `xterm.js`, same-origin WebSocket, permanent host/user/incident banner, paste
   confirmation and the card-limited Insert control. The UI never decides authorization.
4. **21D — isolated deployment:** broker container, SSH CA, one Unix account per operator, sshd restrictions,
   `sudo` I/O logging, `auditd`, off-host recording storage and the network proof that Argus processes cannot reach
   the broker.
5. **21E — exit drill:** replay/refusal tests, idle and absolute expiry, revoke/kill, recording loss, public 404,
   CA revocation and break-glass rehearsal. Only this step may grant `open_terminal:<host>`.

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

Accepted by conantkd on 2026-10-23: build the narrow broker, start with the offline contracts and state machine, and
keep every privileged or connected stage blocked until ACR-0018's phase-16 exit proof. The required independent
safety approval remains a merge gate because the complete design changes least privilege and introduces an SSH CA.

## 6. Applied

- [x] `ARCHITECTURE.md` updated for 21A (new §17.4, §25 OD-17, changelog), version bumped to 1.8.31
- [ ] Later stages update §1.2, §3, §17.1 and §18 when routes, the broker container and recording are built
- [ ] `policies/SECURITY.md`, `NETWORK.md`, `AGENT_PROTOCOL.md`, `PARALLEL_LANES.md`,
      `infrastructure/environment.md`, `guides/TROUBLESHOOTING.md`
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request
