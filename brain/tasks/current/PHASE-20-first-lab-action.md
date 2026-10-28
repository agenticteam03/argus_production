# PHASE-20 — First supervised lab action

| Field | Value |
|---|---|
| Status | in progress: step 1 (the candidate pair, #354), step 2 (execution through the gateway, #355), step 3 (the gateway services, defined, #356) and step 4 (the action path built for the worker, closed by default, X-9); X-2's second window and the release PRs follow |
| Phase | 20 of [NEXT-PHASE](NEXT-PHASE-supervised-remediation.md); pieces X-1..X-7 of the demo's shared coordination file (PR #353) |
| Architecture | [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md), accepted; ACR-0031 applied (#347); no new ACR for this step |
| Branch | `task/T-0053-phase20-candidate`, from `main` (replaces draft #326, 97 commits behind and in conflict) |
| VM lease | none; this step makes no VM change |

## Goal and boundary

Release exactly the reviewed lab pairs, each in its own release PR with two approvals (ACR-0019 §3.13), behind a
human approval, one journaled dispatch, a fresh precheck and a verification. The first pair is `container.start` on
`vm-166/container:argus-lab-cache` (SC-03). No other capability, host or target gains a write route; vm-095 is never a
target. The demo adds two more pairs (`container.restart` on the job worker, `network.restore` on the API), each in
its own release PR.

Phase 19 is on `main` (#324, #347): the gateway core and journal, the socket proxy, the worker's client
(`HttpActionGateway`, tested against the real listener in `tests/test_phase19_gateway_client.py`), the private
approvals and the private login. Draft #326's own client and its test are not carried over: main's client and test
already cover the same behaviour (one send, refusal before the proxy, an ambiguous answer left to `status`).

## STEP T-0053.1 — Freeze the first candidate pair (X-1)

- **Goal:** name and check the only Docker route proposed for the first lab release.
- **Why:** the pair must match the inventory, the action card, the risk table and both gateway ACL layers before a
  release PR can open the write gate.
- **Where:** laptop. **Changes:** `deploy/action_gateway/first-lab-release.candidate.json` and
  `tests/test_phase20_release_candidate.py`; undo by reverting the PR. No VM change.
- **Command:** `python -m pytest -q tests/test_phase20_release_candidate.py`.
- **Expected:** three passing tests: one released pair; the proxy grants one inspect and one write path; the gate is
  still closed and no compose file reads the candidate.
- **If it fails:** compare the candidate's pair with the inventory, the action card and the risk table.

The candidate is not the active gateway configuration (`/etc/argus-v18/action-gateway.json` on the VM) and no compose
service reads it.

## STEP T-0053.2 — Execute through the gateway with a fresh precheck and a verification (X-4)

- **Goal:** the frozen-row `ActionExecutor` dispatches through the reviewed `HttpActionGateway`, with a precheck read
  from the target at execution time and a verification sampled after the action.
- **Why:** phase 18's executor accepted only the fake gateway, and its precheck and verification were test callbacks.
- **Where:** laptop. **Changes:** `argus/actions/live.py` (new: `LivePrecheck`, `LiveVerification`,
  `status_from_observation`); `ActionExecutor` and `OfflineActionPath` accept exactly the fake gateway or the
  reviewed client (`REVIEWED_GATEWAYS`), nothing else; `services/target/service.py` adds `container_id`, Docker's
  full Id; `tests/test_phase20_live_execution.py`. Undo by reverting the PR. No VM change.
- **Command:** `python -m pytest -q tests/test_phase20_live_execution.py`.
- **Expected:** one action through the real gateway listener, never sent twice, verified `recovered_verified`; a
  recreated target is a definite `failed` with no proxy call; any other gateway object is refused.
- **If it fails:** compare the precheck's identity with the proxy's (`unix_transport.py`, the full Id).

**Found on the way:** the gateway's proxy compares Docker's full container Id, but `container.status` reported only
the first 12 characters, so a proposal built from it would have been refused as "target identity changed" on every
real dispatch. The target now also reports `container_id` (full); `id` stays short for its existing readers. The target
service must be redeployed on vm-166 before the first release (X-2/X-3).

**Moved to step 4 (X-9):** the production wiring that builds the path. The policy engine's startup refusal of a
non-empty gate stays with the release PR (X-5), which is what lets the gate name a pair at all.

## STEP T-0053.3 — Define the gateway services and the worker's one path to them (X-3)

- **Goal:** the action gateway and its socket proxy as vm-166 services, and a path from vm-095 that only the worker
  can use; defined, not started.
- **Why:** phase 19 proved the two containers on real images (`tests/test_phase19_real_images.py`) but deployed
  nothing; the release PR needs a reviewed service definition to start.
- **Where:** laptop. **Changes:** `deploy/target/compose.actions.yml` (new, vm-166 only); the tunnel forwards 18705
  only on its address in the new internal network `argus-v18-action` (`deploy/vm-095/tunnel/Dockerfile`,
  `deploy/vm-095/compose.core.yml`: the tunnel and the worker are its only members); `services/action_gateway/run.py`
  replaces a stale proxy socket; `tests/test_phase20_action_services.py`; phase 19's compose guard
  (`tests/test_phase19_gateway_startup.py`) skips the actions file alone. Undo by reverting the PR. No VM change.
- **Command:** `python -m pytest -q tests/test_phase20_action_services.py tests/test_compose_split.py`.
- **Expected:** the proxy alone mounts Docker's socket and has no network; the gateway holds the token and the journal,
  listens on vm-166's loopback only; both read-only, all capabilities dropped, user 65532; no script, env file or
  other compose file loads the actions file; the gateway's name resolves nowhere on vm-095, so the write-gate check
  stays closed.
- **If it fails:** compare the compose file with the real-image test's `docker run` flags.

Why a separate file rather than a profile in `compose.target.yml`: the proxy needs the socket's group
(`ARGUS_DOCKER_GID`, required), and compose interpolates a whole file even for an inactive profile, so a required
variable there would break vm-095's target deploy, which uses the same file.

**Found on the way:** the proxy refused to start when its socket path existed; the socket lives in a named volume, so
any restart or reboot would have left it in a crash loop. It now removes a socket that nobody answers on, and still
refuses a live socket or a path that is not a socket.

**Deferred to the windows, on purpose:**
- X-2 (the deploy window): rebuild and restart `argus-v18-tunnel` explicitly (the deploy hint for `deploy/vm-095/`
  names only the agent, worker and scheduler), and recreate the worker so it joins `argus-v18-action`; redeploy the
  target on vm-166 (`container_id`, X-4). The write-gate check stays CLOSED: no action container, mount or credential.
- X-5 (the first release PR's window): the action token, created on the VM and never in the repo, at
  `/opt/argus-v18/secrets/action/action_token` on vm-166 (owner 65532, 0400) and at
  `/opt/argus-v18/secrets/agent/action_token` on vm-095 (the worker's folder, as the isolation proof places it); the
  active `/etc/argus-v18/action-gateway.json` on vm-166; `permitopen="127.0.0.1:18705"` on vm-166's tunnel account;
  the network alias `argus-v18-action-gateway` for the tunnel on `argus-v18-action`; the worker's gateway URL; the
  services started; the write-gate check changed to expect exactly this; `ARCHITECTURE.md` and ACR-0019 §6.

## STEP T-0053.4 — Build the action path for the worker, closed by default (X-9)

- **Goal:** the worker constructs the supervised-action path from parts that are already reviewed, and only when it is
  asked to and the write gate names a pair.
- **Why:** after X-4 nothing in `argus/` built `OfflineActionPath`, `LivePrecheck` or `HttpActionGateway`, so opening a
  pair would have changed a file and nothing else. (This was between rows X-4 and X-5 of the coordination file and had no
  row of its own; it is X-9 now.)
- **Where:** laptop. **Changes:** `argus/infrastructure/action_wiring.py` (new); `Settings` and `build()` in
  `argus/infrastructure/wiring.py`; `identity_of` factored out of `LivePrecheck` in `argus/actions/live.py`;
  `tests/test_x9_action_path_wiring.py`. Undo by reverting the PR. No VM change.
- **Built only when** `ARGUS_ACTION_PATH=1` **and** `write_gate.open` names a pair, and the runner is `langgraph`. With
  the flag on and the gate open, a missing gateway address, token file, judge key or action table stops the start and
  names every missing piece; it is never ignored. The default is off, and on `main` the policy engine still refuses a
  non-empty gate.
- **Decision, written here:** the proposer is deterministic. ACR-0019 lets the model draft a proposal; this version builds
  it from the reviewed candidate, the action card and a fresh audited `container.status` read, and the judge (a second
  model) still reviews the frozen result. That is narrower than the ACR allows. It proposes only for the argument-less
  actions `container.start` and `container.restart`, and only for an incident class with a reviewed verification signal
  (`dependency_unavailable`: `dependency_probe_min`, healthy at 1). Anything else is no proposal, and the incident
  escalates as it does today. `network.restore` (two required networks) and the stalled-worker class are not here yet.
- **The API's approval routes:** the private login, the approval and the hold routes are mounted only while
  `write_gate.open` names a pair (`approval_rows`), whatever `ARGUS_ACTION_PATH` says (the API has no action token).
  Before, production never mounted them, so no one could approve. Their guards are unchanged.
- **Reads and checks fail in the safe direction:** the precheck treats "cannot tell whether the class still matches" as
  not matching (nothing is sent); the verification treats it as still firing (no recovery is claimed); a missing,
  stale or non-finite sample is unknown, never healthy.
- **Command:** `python -m pytest -q tests/test_x9_action_path_wiring.py`.
- **Expected:** the units (gate, proposer, sampler, detector checks, judge context, build decisions, Settings, the
  `build()` hook) and one run from diagnosis to `recovered_verified` through the real gateway listener, with one
  dispatch.
- **If it fails:** compare the proposal with what `OfflineActionPath.propose()` validates (`argus/orchestration/action_path.py`).

**Found on the way:** `OfflineActionPath.precheck`, `execute` and `verify` took their decision time before the read and
then refused a read stamped after it, so every real precheck and verification would have failed (CI on Linux showed
it; Windows' coarse clock hid it). Each is now judged at a time taken after its read.

**Not covered, on purpose:** the approval notice of #367 is not wired (it needs the Alertmanager address in the worker);
the host lease is not read by code (ACR-0019 section 3.11: by process); the judge and Prometheus are doubles in the
test, so their real behaviour is for the live proof.

## Still required (each its own PR)

1. **X-2:** one deploy window on vm-095 (phase 19 and the corpus), with the leases.
2. **X-5..X-7:** one release PR per pair, opening it in `config/policy.yaml`, the gateway configuration and the
   standing write-gate test, which keeps every unreleased pair closed. Before each: the hard checks
   (`unauthorized_actions`, `actions_on_forbidden_targets`, `action_without_valid_approval`, `harmful_actions`) at 0,
   and a lease-bound VM block with `nonint-check.sh` before and after and a rehearsed rollback that empties the gate
   and stops the gateway.
3. Live proof: SC-03 on the real lab: a correct proposal, judge agreement, an authenticated approval, exactly one
   dispatch, the prediction met and `recovered_verified`; evidence without secrets.

## Current result

Step 1: red seen (`FileNotFoundError`, the candidate absent), then green.
Step 2: red seen (`ModuleNotFoundError: argus.actions.live`), then green.
Step 3: red seen (`FileNotFoundError`, `compose.actions.yml` absent), then green.
Step 4: written code first, then tests; the tests were mutation-checked (a sampler that always says healthy, and a proposer that ignores the gate, each fail them), then green.
