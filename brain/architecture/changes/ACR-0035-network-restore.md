# ACR-0035 — `network.restore`: reconnect a lab container to its expected network and leave the wrong one

Extends [ACR-0019](ACR-0019-human-approved-remediation.md) (§3.3 the catalogue, §3.4 the cards, §3.7 the risk colours,
§3.9 the execution path, §3.13 the release scope). TASK-89 applies it with the first and only `network.restore` release
pair on the lab API, with the exact route and network names in the candidate file.

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-27 |
| Accepted by | Implementing release PR TASK-89; developer approval and Conan's second approval are required before merge |
| Second approval (safety principle only) | **required** for the write gate and least-privilege body rule; Conan's approval is the second approval on TASK-89 (AGENT_PROTOCOL §4) |
| Architecture version | `1.8.45` (phase 20, X-8; this implementing release) |
| Task / PR | TASK-89 (lane S2b), third release PR |

## 1. Detect and explain

A container on the wrong Docker network cannot reach what it depends on, and Argus can diagnose that but not repair
it. Scenario SC-07 is the case: `argus-lab-client` is declared on `argus-lab-app` and its backend, `argus-lab-backend`,
is declared there too, but the backend is running on `argus-lab-iso`. The link from the client to the backend is
`broken` (`network.link_states`, ACR-0025) while both containers are healthy.

What the code has today (`argus/actions/catalog.py`, `config/actions/`, `services/action_gateway/`):
- the cards and the released-route check cover `container.start`, `stop`, `restart`, `pause` and `unpause`
  (`validated_pairs` in `core.py` accepts only those five verbs); the risk table adds `update_resources`;
- the catalogue also lists `container.network_connect` and `container.network_disconnect` (named in ACR-0019 §3.3),
  but they have no action card, no row in `ACTION_ROUTES`, no risk row and no gateway route. They cannot execute, and
  two separate actions would put two approvals, two ledger rows and a half-repaired state in the way of one repair;
- the socket proxy forwards a POST only with an empty body (`Content-Length` other than `0` is answered 400), and
  the gateway's worker-facing body carries no network names, so Docker's network calls, which need a JSON body naming
  the container, cannot pass.

So a wrong-network fault ends in "escalate to a human", who repairs it by hand with no link to the incident.

## 2. Why the current architecture is insufficient

- §12.2 and ACR-0019 §3.3 intend network actions but define them as two independent actions, "connect to an allowed
  network" and "disconnect from a network". The order matters (disconnecting first strands the container with no
  route; connecting only leaves the wrong network attached, so a name can resolve to the wrong peer) and so does
  being able to stop between the two. As two proposals the order is up to two approvals.
- §4.5 and §13.3 say the gateway accepts exact `(route, target)` pairs, and the proxy has "path ACLs". A network
  route's path (`/networks/{id}/connect`) carries the network, not the container, and the container is in the body.
  The exact-route rule is therefore not enough: the body is the part that says what is touched. The architecture
  has no rule for validating a body, nor for a release entry that names parameters.
- §14.8's contract (identity, dispatch, reconcile) has one dispatch per action. This action ends in two Docker calls
  and must stay inside that contract: the worker makes **one** call, and the two steps belong to the gateway, which
  can order them, journal them and refuse to repeat one.

## 3. Smallest reasonable change

### 3.1 The action (§12.2, ACR-0019 §3.3)

ONE action, `network.restore` (model name `restore_network`, intent `network`), replacing the unreleased
`container.network_connect` and `container.network_disconnect` entries (nothing refers to them: no card, no route).

| Parameter | Meaning | Must be |
|---|---|---|
| `connect_network` | the network to join | declared for the target in the inventory (`networks:`, and in the service card's `allowed_networks`) and **not** one the target is on now |
| `disconnect_network` | the network to leave | one the target is on now and that is **not** declared for it |

- Both are names from the inventory, never free text. Neither may be the default `bridge`, `host` or `none`, in
  either parameter, and the same name cannot appear in both.
- Both are required: this action repairs a wrong-network fault, which is always "on the wrong one, not on the right
  one". A container that only lacks a declared network, or only carries an extra one, has no card here and is a
  `suggest_action` (ACR-0019 §3.3); that keeps the action's meaning narrow enough to approve.
- Scope: lab containers `argus-lab-*` on `vm-166` only, the same target pattern as the other released actions. No
  action on `vm-095` (ACR-0019 §5, answer 4), none on Argus's own services, Prometheus, the gateways or the probes.

### 3.2 One worker call; the gateway does connect, then disconnect (§14.4, §14.8)

One proposal, one approval, **one worker call**, like every other action. The worker's ledger keeps its existing
states (`attempting`, then `confirmed`, `failed` or `indeterminate`): no new state and no migration.

- The worker sends the gateway one request for `network.restore`: the capability, the target, the frozen identity
  and the action id (the same fields as the other actions), plus the two network names from the frozen proposal.
  The route is keyed by the container, like the others (`/containers/{name}/network-restore`).
- The gateway checks the capability, the target, the identity **and the two names** against its release entry, which
  names the exact `connect_network` and `disconnect_network`. Then it makes the two Docker calls itself, **connect
  first, then disconnect**, each with the exact body it builds (§3.5). A failed connect disconnects nothing: the
  container always keeps a path.
- The gateway journal records two insert-only events under the same action id, `connect` and `disconnect`; a repeated
  `(action_id, step)` is refused (409), as a repeated action id is today. Nothing is sent twice.
- The answer to the worker: `confirmed` only after both calls succeeded; `failed` if the connect failed (nothing else
  was done) or the gateway refused before any call; and if the answer is lost after the connect, the action stays
  `received` (ambiguous) and the worker's reconcile asks the gateway journal by action id.
- **A half state is never repaired automatically.** "Connected, not disconnected" (the connect confirmed, the
  disconnect failed or its answer lost) is reported as `indeterminate` and escalates to a human, never an automatic
  retry (§14.4). The container is then on both networks, never on none.

### 3.3 Preconditions from live state (the action card, ACR-0019 §3.4)

`config/actions/network.restore.yaml`, evaluated by the existing interpreter on fresh reads at the precheck and
again just before each call:
- the target is running; its container id equals the frozen identity (`identity_fields: [container_id]`);
- `connect_network` is declared for the target and the target is **not** on it; `disconnect_network` is **not**
  declared for the target and the target **is** on it; neither is `bridge`, `host` or `none`;
- the target's service card lists `network.restore` in `safe_actions` and not in `never`;
- the target would keep at least one declared network after the action (so it can never be left with none);
- the declared dependent of the target (the other end of the link, below) is running, so a verify result means
  something.

`useful_when`: a declared link to the target is `broken` and the target is on a network it does not declare.
`not_useful_when`: the target is stopped or crash-looping (a restart or start action is the card for that), the link
is broken for another reason (the target refuses the connection while on the right network), or the network the
target should be on does not exist (a human creates networks).

### 3.4 Verification and rollback (§15.1)

- **Verify:** the link from the declared dependent to this target, as recorded by the link recorder
  (`application/links.py`, `link_event`), is `ok` again on a sample observed after the action completed, within the
  card's window (120 s, the same window as the SC-03 prediction). A pre-action sample never counts (§15.1). `slow` or
  `unknown` is not `ok`. The proposal's `prediction` names this link, so a recovery of the target alone does not
  satisfy it.
- **Rollback:** none, and none is automated. A person restores the old state by hand (`docker network`), outside
  Argus. The swapped action is **not** a valid proposal: its connect network (the old wrong one) is not declared for the
  target and its disconnect network (the right one) is, so two of the card's preconditions fail by design, and an
  action that reattaches a container to the wrong network on purpose is not one to automate. The approver sees
  **Reversible: no**, with the note that connections on the wrong network are cut. If a swap is ever wanted it needs
  its own action with its own preconditions and its own ACR.

### 3.5 The gateway: a release entry with the two names, and an exact body (§4.5, §13.3)

The worker-facing side does not change shape: the same bearer token, `X-Argus-Action-Id`, journal and identity check
before the write, and an answer cut down to a status. What changes is inside the gateway and its proxy:

- **The release entry** becomes `(capability, target, connect_network, disconnect_network)` for `network.restore`.
  The gateway refuses a call whose two names are not exactly the entry's. The names come from the frozen proposal and
  were checked against live state at the precheck; the release pins them again, so a release can never allow "any
  network".
- **The Docker calls** are `POST /networks/{id}/connect` and `POST /networks/{id}/disconnect`, with `{id}` the
  **configured network name** from the release entry (the name Docker accepts in that position), never a
  caller-chosen string and not an id looked up at run time. The gateway code does the same. The gateway builds the body itself:
  **exactly** `{"Container": "<container id>"}`, one key and the id of the target from the frozen identity, no
  `EndpointConfig`, aliases, `IPAMConfig` or `Force`. The worker never sends Docker's JSON.
- **The proxy** accepts a body only on those two routes and only that exact shape (compared with the bytes it expects
  for that `(action, step)`, at most 256 bytes); any other body, or any body on any other route, is refused (403),
  as today.
- `validated_pairs` accepts `network.restore` only for `argus-lab-*` on the lab host, and refuses a network named
  `bridge`, `host` or `none`, or one whose inspect shows it is not a user-defined lab network.

### 3.6 Risk colour (`config/risk.yaml`, ACR-0019 §3.7)

| Target kind | Colour | Why |
|---|---|---|
| `stateless` | amber | not reversible by Argus (a person restores it), and it cuts the connections on the wrong network |
| `stateful` | red | a stateful service dropping peers can corrupt in-flight work |
| `proxy` | red | a proxy is every client's path; a wrong move is an outage |
| `database` | **forbidden** | never offered; a database's networks are changed by humans only |

The colour can only go up (§3.7). A red proposal needs the approver to type the target's name.

### 3.7 Safety principles touched

- **Write gate:** a new capability. It is released per `(capability, target, connect_network, disconnect_network)` by
  a reviewed edit to `write_gate.open`; the standing test (`tests/test_write_gate_standing.py`) covers it unreleased.
- **Least privilege:** the proxy accepts a body for the first time. It does so for two paths and one exact shape,
  built by the gateway.
- Model-out-of-the-path (ACR-0019 §3.9) is unchanged: the dispatch reads frozen rows only; the networks to connect and
  disconnect are in the frozen proposal and are checked against live state at the precheck.

**Alternatives considered**
- A: **keep the architecture and work around it.** Leave the fault to a human with `docker network` by hand. Safe,
  and what happens today, but it breaks the loop (no approval, no ledger, no verification) and the SC-07 repair stays
  manual. Rejected as the end state; it remains the fallback.
- B: **restart the container.** A restart keeps its networks (the network settings are part of the container, not
  the process), so the container comes back on the wrong network, and it interrupts a healthy service. It also
  fails ACR-0019's own "restarting the victim instead of the cause" rule. Rejected.
- C: **a compose redeploy** (re-create the service from its compose file, which puts it on the declared networks).
  It fixes the cause too, but it needs a Docker Compose client or a project-level write on the host, re-creates the
  container (new id, lost state, a different identity from the one approved), touches every service in the file and
  needs a far wider gateway than two exact routes. It is the `deployment.rollback` family, with its own ACR.
  Rejected here.
- D: **keep two actions (connect and disconnect).** Each is simple, but a repair needs two approvals in an order
  nothing enforces, and a crash or a denial between them leaves the half-repaired state with no owner. Rejected.
- E: **two worker calls under one proposal, with new ledger states (`connected`, `disconnected`).** Closer to the
  worker owning the order, but it needs a two-step reconcile in the worker's execution path, new states and a
  migration. Rejected: the gateway can keep the same safety (connect first, no repeat, never left with no network)
  with the worker's ledger unchanged.

## 4. Consequences

- **Code (later PRs, none in this one):** `argus/actions/catalog.py` (replace the two entries, add the route `/containers/{name}/network-restore`, the one
  route name in the catalogue, the worker's call and the gateway);
  `config/actions/network.restore.yaml`; `config/risk.yaml`; `argus/actions/gateway_client.py` (the two names added to
  the worker's one call); `services/action_gateway/` (the release entry with the two names, the gateway's two Docker
  calls, the journal's `step`, the proxy's exact body check); the service cards' `safe_actions` for the released
  container. **No ledger state, no migration, no change to `argus/actions/execution.py`.**
- **Tests before any release:** red first. Both parameters validated against the inventory; never `bridge`, `host`
  or `none`; a network the target is already on, or declared for it, refused for disconnect; the same name in both
  refused; a call whose names differ from the release entry refused; connect before disconnect, always; a failed
  connect disconnects nothing; a lost answer after the connect leaves `received` and the journal answers by id; a
  connect without its disconnect is `indeterminate` and escalates, with no retry; the proxy refuses any body but the
  exact one on the two routes and any body at all elsewhere; the journal refuses a repeated `(action_id, step)`; a
  database target is forbidden; the verify reads the link, not the target; the approver card shows `reversible: no`; the
  standing write-gate test with the pair unreleased.
- **Other architecture sections affected:** §4.5, §12.2, §13.3, §14.4, §14.8 (the example: one dispatch, two
  gateway steps), §15.1 and the changelog; ACR-0019 §3.3's list (the two names become one).
- **Risk:** a wrong network chosen for a container on a lab host. Limited by: both names coming from the inventory,
  the live-state preconditions, the one-network floor, the amber and red colours with the judge, the exact body, lab
  scope and the verify on the link. A crash or lost answer mid-way leaves the container on both networks (a state a human sees,
  reported `indeterminate`), never on none.
- **How to reverse it:** remove the `network.restore` entry from `write_gate.open` (the action is then refused at
  once); the proxy's body exception exists only for a released network entry, so an empty release map restores
  today's bodyless rule. Removing the catalogue entry and its card is a code change.
- **Safety principles touched:** yes, the write gate and least privilege (§3.7). Second approval required.

## 5. Decision

Proposed. Decisions taken by the manager on 2026-10-27, written here for the reviewer:
1. **The ledger keeps its existing states.** `network.restore` is one worker call; the connect-then-disconnect order,
   the journal and the half-state report belong to the gateway (section 3.2). No `connected` / `disconnected` state.
2. **The first and only release for the demo** is `network.restore` on `vm-166/container:argus-lab-api`, with the
   exact names `connect_network: argus-lab-app` and `disconnect_network: argus-lab-iso` (the names are set in the
   release PR, with two reviewers). SC-07's backend can follow. There is no automatic rollback and no release entry
   with the names swapped: a person restores the old state by hand, and the card shows `reversible: no` (section 3.4).
3. **The dependent of the release target.** Section 3.4 verifies the link from the declared dependent to the target.
   TASK-89 adds `vm-166/container:argus-lab-api` to `argus-lab-client`'s `depends_on` list while preserving its existing
   backend dependency. The inventory renderer provides a separate TCP/8080 probe and link record for each edge; the
   network restore prediction and post-action verification use the API edge.
4. **Where the networks come from.** The SC-07 injection on `vm-166` moves `argus-lab-api` from `argus-lab-app` to
   `argus-lab-iso`. The release pins that exact pair. The connect-first sequence restores the API's declared network;
   no deployment or VM action is part of this PR.

## 6. Applied

- [x] `ARCHITECTURE.md` updated (§4.5, §12.2, §13.3, §14.4, §14.8, §15.1, changelog), version bumped to 1.8.45 (X-8)
- [x] ACR-0019 §3.3's catalogue list updated to the single action
- [x] the action card, risk rows, gateway release entry, calls and journal steps, with their tests (implementation files were completed in the preceding S2 tasks)
- [x] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
- [ ] a release PR for the first `(network.restore, target)` pair, two reviewers (ACR-0019 §3.13)
