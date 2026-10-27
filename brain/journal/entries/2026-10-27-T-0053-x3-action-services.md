## 2026-10-27 - T-0053: the gateway services on vm-166 and the worker's one path to them (X-3)

Type: implementation
Who: conantkd (+ agent)
Context: phase 19 proved the gateway and the socket proxy as two containers on real images but deployed nothing; the
release PR needs a reviewed service definition to start, and the standing write-gate check must stay closed until then.
Decision / result:
- `deploy/target/compose.actions.yml` (vm-166 only, loaded by no script or env file): the proxy alone mounts Docker's
  socket and has no network; the gateway holds the token and the journal and listens on vm-166's loopback (18705);
  both read-only, all capabilities dropped, user 65532.
- A separate file, not a profile: the proxy needs the socket's group (`ARGUS_DOCKER_GID`, required), and compose
  interpolates a whole file even for an inactive profile, so the shared `compose.target.yml` would break on vm-095.
- vm-095: the tunnel forwards 18705 only on its pinned address in the new internal network `argus-v18-action`, whose
  only other member is the worker. The gateway's name gets no alias yet, so the write-gate check still reports CLOSED.
- Found on the way: the proxy refused to start when its socket path existed; in a named volume a restart or reboot
  would have crash-looped it. It now removes a socket nobody answers on, and still refuses a live one or a non-socket.
- Phase 19's guard that no compose file names the gateway or `action_token` now skips `compose.actions.yml` alone;
  the new test proves nothing loads that file, and every other compose file still names neither.
- My rows: X-3 building, X-4 PR #355.
Consequences: X-2's window rebuilds the tunnel explicitly and recreates the worker. X-5's window creates the action
token on both VMs (never in the repo), the active gateway configuration, the tunnel account's permit, the gateway alias
and the worker's URL, starts the services and changes the write-gate check to expect exactly them.
References: [PHASE-20 task](../../tasks/current/PHASE-20-first-lab-action.md), ACR-0019 §3.9.

### Test state

Red first: `tests/test_phase20_action_services.py` failed with `compose.actions.yml` absent. Then green, with the compose
split and every test that reads a compose file, a Dockerfile, the tunnel or the gateway package (all green). The two
stale-socket tests need Unix sockets: skipped on Windows, run in CI.

### Next step

X-2: the deploy window on vm-095 and vm-166 (phase 19, the corpus, the tunnel and worker, the target's `container_id`),
with the leases; tell juanbetancurm when they are released.
