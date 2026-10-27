# ACR-0035 — `network.restore`: reconnect a lab container to its expected network and leave the wrong one

Extends [ACR-0019](ACR-0019-human-approved-remediation.md) (§3.3 the catalogue, §3.4 the cards, §3.7 the risk colours,
§3.9 the execution path, §3.13 the release scope). It adds one action to the closed catalogue and two exact routes to
the action gateway. Nothing is released by this ACR: `write_gate.open` stays empty until a release PR names the pair.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-27 |
| Accepted by | — |
| Second approval (safety principle only) | **required**: the write gate (a new capability and two new gateway routes) and least privilege (the proxy starts to accept a request body). To be given in the PR that accepts this ACR (AGENT_PROTOCOL §4) |
| Architecture version | from `1.8.40` → the next free version when applied (the PR that merges second renumbers) |
| Task / PR | TASK-56 (fast track, lane S2) · PR to be opened by the manager |

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
- the socket proxy forwards a POST only with an empty body (`Content-Length` other than `0` is answered 400), so
  Docker's network routes, which need a JSON body naming the container, cannot pass.

So a wrong-network fault ends in "escalate to a human", who repairs it by hand with no link to the incident.

## 2. Why the current architecture is insufficient

- §12.2 and ACR-0019 §3.3 intend network actions but define them as two independent actions, "connect to an allowed
  network" and "disconnect from a network". The order matters (disconnecting first strands the container with no
  route; connecting only leaves the wrong network attached, so a name can resolve to the wrong peer) and so does
  being able to stop between the two. As two proposals the order is up to two approvals.
- §4.5 and §13.3 say the gateway accepts exact `(route, target)` pairs, and the proxy has "path ACLs". A network
  route's path (`/networks/{id}/connect`) carries the network, not the container, and the container is in the body.
  The exact-route rule is therefore not enough: the body is the part that says what is touched. The architecture
  has no rule for validating a body.
- §14.8's contract (identity, dispatch, reconcile) has one dispatch per action. This action makes two Docker calls
  and needs a reconcile that can tell "connected, not yet disconnected" from "nothing done".

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

### 3.2 Order, ledger and reconciliation (§14.4, §14.8)

One proposal, one approval, **two Docker calls**, always in this order: connect, then disconnect.

- The ledger gets two new intermediate states for this capability: `connected` (the connect call is confirmed, the
  disconnect is not) and then `disconnected`, which is the terminal success state (it maps to `confirmed` for the
  verification and the record). Each transition is written, with its audit row, before the next call is made.
- A crash or an ambiguous answer between the calls is **reconciled, not repeated**: `reconcile(action_id, target,
  attempted_at)` reads the gateway journal first (below), then the live state of the target's networks through the
  read executors. "Connected to `connect_network`, still on `disconnect_network`" resumes at the second call;
  "on `connect_network`, not on `disconnect_network`" is `disconnected`; anything else is `indeterminate` and
  escalates (§14.4, never an automatic retry). A refused or failed connect leaves the ledger `failed` and nothing is
  disconnected: the container always keeps a path.
- The gateway journal records each call under the same `action_id` with a step (`connect`, `disconnect`); the
  existing append-only tables get one `step` column. A repeated `(action_id, step)` is answered 409, as a repeated
  action id is today.

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
- **Rollback:** the same action with the two names swapped (`connect_network` becomes the old `disconnect_network`
  and the reverse). The swapped proposal passes the same preconditions, so the rollback is itself a proposal a human
  approves; it is never run on its own. Reversible: yes, shown to the approver, with a note that connections made on
  the wrong network are cut either way.

### 3.5 The gateway: two exact routes and an exact body (§4.5, §13.3)

Today the proxy refuses any POST with a body. The change is the smallest that lets Docker's network calls through
and no more:

- New exact routes, per target: `POST /networks/{id}/connect` and `POST /networks/{id}/disconnect`, where `{id}` is
  the network's identity as the inventory-bound read returns it (not a name the caller chooses at call time), and
  the released pair names the network. A released entry becomes `(capability, target, network)` with the two routes.
- The only body accepted on these two routes is **exactly** `{"Container": "<container id>"}`: one key, a string
  value, the id of the target from the frozen identity, no `EndpointConfig`, no aliases, no `IPAMConfig`, no `Force`
  on disconnect. The gateway builds the body itself from the frozen proposal; the worker never sends Docker's JSON.
  The proxy compares the body with the expected bytes for that `(action, step)` and answers 403 on any difference.
  The body limit is small (256 bytes). Every other route keeps today's rule: no body.
- `validated_pairs` accepts the capability `network.restore` only for `argus-lab-*` on the lab host, and refuses a
  network named `bridge`, `host` or `none`, or one whose inspect shows it is not a user-defined lab network.
- Nothing else changes: bearer token, `X-Argus-Action-Id`, the journal, the identity check before the write, the
  answer cut down to a status code.

### 3.6 Risk colour (`config/risk.yaml`, ACR-0019 §3.7)

| Target kind | Colour | Why |
|---|---|---|
| `stateless` | amber | reversible, but it cuts the connections on the wrong network |
| `stateful` | red | a stateful service dropping peers can corrupt in-flight work |
| `proxy` | red | a proxy is every client's path; a wrong move is an outage |
| `database` | **forbidden** | never offered; a database's networks are changed by humans only |

The colour can only go up (§3.7). A red proposal needs the approver to type the target's name.

### 3.7 Safety principles touched

- **Write gate:** a new capability and two new routes. Both are released per `(capability, target)` by a reviewed
  edit to `write_gate.open`; the standing test (`tests/test_write_gate_standing.py`) covers them unreleased.
- **Least privilege:** the proxy accepts a body for the first time. It does so for two paths and one exact shape.
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

## 4. Consequences

- **Code (later PRs, none in this one):** `argus/actions/catalog.py` (replace the two entries, add the route);
  `config/actions/network.restore.yaml`; `config/risk.yaml`; `argus/actions/gateway_client.py` (two calls, bodyless
  from the worker's side); `services/action_gateway/` (`validated_pairs`, the journal's `step`, the proxy's exact body
  check); the ledger's `connected` and `disconnected` states and their reconcile; the service cards' `safe_actions`
  for the lab's SC-07 containers.
- **Tests before any release:** red first. Both parameters validated against the inventory; never `bridge`, `host`
  or `none`; a network the target is already on, or declared for it, refused for disconnect; the same name in both
  refused; connect before disconnect, always; a crash between the calls reconciles to `disconnected` without a second
  connect; a failed connect disconnects nothing; the proxy refuses any body but the exact one on the two routes and
  any body at all elsewhere; the journal refuses a repeated `(action_id, step)`; a database target is forbidden; the
  verify reads the link, not the target; the rollback is the swapped proposal; the standing write-gate test with the
  pair unreleased.
- **Other architecture sections affected:** §4.5, §12.2, §13.3, §14.4, §14.8 (a two-step example), §15.1 and the
  changelog; ACR-0019 §3.3's list (the two names become one).
- **Risk:** a wrong network chosen for a container on a lab host. Limited by: both names coming from the inventory,
  the live-state preconditions, the one-network floor, the amber and red colours with the judge, the exact body, lab
  scope and the verify on the link. A crash mid-way leaves the container on both networks (a state a human can see),
  never on none.
- **How to reverse it:** remove the `network.restore` pair from `write_gate.open` (the action is then refused at
  once); the proxy's body exception is only for released network routes, so an empty release map restores today's
  bodyless rule. Removing the catalogue entry and its card is a code change.
- **Safety principles touched:** yes, the write gate and least privilege (§3.7). Second approval required.

## 5. Decision

Proposed. Open questions for the reviewer:
1. Is `connected` / `disconnected` the right pair of ledger names, or should the ledger keep its three terminal states
   and record the step in a column instead? (The text above keeps the card's names.)
2. Should the first release be `vm-166/container:argus-lab-backend` only (SC-07), as ACR-0019 started with one pair?
   This ACR assumes yes and leaves the pair to the release PR.

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§4.5, §12.2, §13.3, §14.4, §14.8, §15.1, changelog), version bumped
- [ ] ACR-0019 §3.3's catalogue list updated to the single action
- [ ] the action card, the risk rows, the gateway routes and the ledger states, with their tests
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
- [ ] a release PR for the first `(network.restore, target)` pair, two reviewers (ACR-0019 §3.13)
