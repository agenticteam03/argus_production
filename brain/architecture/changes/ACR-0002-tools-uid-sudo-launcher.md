# ACR-0002 — The tools server's UID switch is a fixed sudo launcher (§12.6), and OD-3 is decided (§25)

An Architecture Change Record is the **only** way to change `brain/architecture/ARCHITECTURE.md`. ACRs are never
fast-tracked: this one changes how a safety principle (secrets) is enforced, so it needs a second team member's
approval in its pull request.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-09 |
| Accepted by | — |
| Second approval (safety principle only) | required (secrets) — in PR #36 |
| Architecture version | from `1.8.1` → `1.8.2` |
| Task / PR | T-0021 · PR #36 |

## 1. Detect and explain

T-0021 puts the target-side reads in an MCP tools process that alone can read the executor tokens. §12.6 says that
process runs under its own UID, "dropped at spawn (`setpriv`/`gosu`)". That cannot work as written: the worker runs
as the non-root user `argus`, and a non-root process cannot switch to another UID with `setpriv` or `gosu`. Running
the worker as root so it could switch would let the worker read the tokens itself, which is what §12.6 forbids.

T-0021 therefore uses one sudo rule (`deploy/agent/argus-tools.sudoers`): `argus` may start exactly the root-owned
launcher `/usr/local/bin/argus-tools-server` as `argus-tools`, with no arguments. Verified on vm-095 (2026-10-08,
`execution/history/T-0021/step-05/evidence.md`): TOOLS ISOLATION OK, SC-02 diagnosed through the tools process.

The review of PR #36 (`conantkd`) found a hole in the first launcher and reproduced it with fake tokens: sudo keeps
the caller's working folder, and `python -m` puts that folder first on `sys.path`. The worker can write to `/tmp`,
so it could plant its own `argus` package there and have it run as `argus-tools`, which can read every token. Fixed
in the same PR: the launcher changes to `/` and runs `python -I -u`. `isolation_check` now probes exactly this (it
plants a package and starts the launcher from that folder). On the agent image: the old launcher gives
`FAIL the launcher ignores code planted in the caller's folder ... TOOLS ISOLATION STOP`; the fixed one gives
`TOOLS ISOLATION OK`.

The same task ran the OD-3 benchmark (§25) on vm-095: 30 alternating pairs per capability, run as `argus-tools`.
`container.status`: overhead p50 2.1 ms / **p95 45.7 ms**; `container.logs`: p50 2.6 ms / **p95 43.1 ms**; no failed
read. The budget is 100 ms.

## 2. Why the current architecture is insufficient

- **§12.6, first bullet:** *"The tools server is spawned by `argus-worker` as a child process under a dedicated
  non-root UID (`argus-tools`), dropped at spawn (`setpriv`/`gosu`)."* "Dropped at spawn" needs a root parent. The
  worker is not root, and it must not be (second bullet: "The worker UID cannot read them").
- **§12.6** does not say what the start of the tools process must guard against. The review showed that the
  mechanism, not only the UID, decides whether the tokens are safe: the caller's working folder and environment must
  not reach the process that runs as `argus-tools`.
- **§25 OD-3** is still open, although its benchmark has run.

## 3. Smallest reasonable change

**§12.6, first bullet**, before → after:

> before: The tools server is spawned by `argus-worker` as a child process under a dedicated non-root UID
> (`argus-tools`), dropped at spawn (`setpriv`/`gosu`).
>
> after: The tools server is spawned by `argus-worker` as a child process under a dedicated non-root UID
> (`argus-tools`). The worker is not root, so the switch is **one fixed sudo rule** (decided by ACR-0002): the
> worker UID may start exactly one root-owned launcher as `argus-tools`, with no arguments, and nothing else. The
> launcher sets its own environment, leaves the caller's working folder (`cd /`) and runs Python isolated (`-I`), so
> nothing the worker can write (its working folder, `PYTHON*` variables) runs as `argus-tools`. The credential
> isolation check starts the launcher from a folder holding a planted package and expects the real server.

**§12.5** (the sentence about OD-3), before → after:

> before: Its retention is decided by a benchmark (**Open Decision OD-3**, §25).
>
> after: Its retention was decided by a benchmark (**OD-3**, §25: kept, ACR-0002).

**§25 OD-3**, the "current state" column, before → after:

> before: benchmark in step 8: keep MCP if p95 overhead < 100 ms per call, no eval regression, and the
> credential-isolation test passes; otherwise `TOOL_CATALOGUE=direct` with process isolation by other means
>
> after: **decided by ACR-0002 (2026-10-09): keep MCP.** On vm-095, p95 overhead 45.7 ms (`container.status`) and
> 43.1 ms (`container.logs`) per read, under the 100 ms budget; the credential-isolation check passes. `direct` stays
> as the rollback. The "no eval regression" part is checked when the §21.2 evaluation exists (Phase 12); until then,
> SC-02 run through the tools process on vm-095 gave the expected diagnosis.

**Changelog:** `1.8.2 · 2026-10-09 · the tools server's UID switch is a fixed sudo launcher (cd /, python -I);
OD-3 decided: keep MCP · ACR-0002`.

**Alternatives considered:**
- **A — Keep `setpriv`/`gosu` and run the worker as root.** Rejected: a root worker can read the tokens, so a
  compromised worker would have them; that removes the isolation §12.6 exists for.
- **B — A root supervisor in the worker container that starts both the worker and the tools process.** Rejected
  for now: one more long-lived root process in the container, and the worker would need a channel to it to get a
  dead tools process restarted (today it restarts its own child). It remains possible later without changing the
  tools server.
- **C — The tools server as its own container (a sidecar), reached over a socket.** Rejected for this release:
  stdio becomes a network transport that must be authenticated, and a new container must be operated on each host.
  It would be the natural step if OD-12 (one target agent per host) is ever decided.
- **D — Keep the architecture text and the sudo rule without an ACR.** Rejected: it would change the mechanism behind
  a safety principle silently (AGENT_PROTOCOL §4).

## 4. Consequences

- Code, tests, deployment and other architecture sections affected: `deploy/agent/argus-tools-server`,
  `deploy/agent/argus-tools.sudoers`, `Dockerfile` (sudo and the two users), `argus/tooling/isolation_check.py`
  (the planted-package probe), `tests/test_tool_isolation.py`. §12.5 and §25 OD-3 as above.
- Risk: sudo is one more setuid program in the worker image. It allows one fixed command without arguments, with a
  reset environment; `isolation_check` proves the refusals (`cat` of a token, arguments, root) and the planted
  package on each host where the worker runs in `mcp` mode.
- How to reverse it: `ARGUS_TOOL_CATALOGUE=direct` and the token ownership back to the worker (rollback block R in
  `execution/history/T-0021/step-05/`); the architecture text goes back with a new ACR.
- Does it touch a **safety principle** (read-only, write gate, host isolation, evidence integrity, secrets)?
  **yes — secrets.** The principle itself does not change (only `argus-tools` can read the executor tokens); the
  mechanism that enforces it does.

## 5. Decision

Proposed by `juanbetancurm`: start the tools server through one fixed sudo launcher that leaves the caller's folder
and runs Python isolated, and close OD-3 with "keep MCP". Waiting for a second team member's approval in PR #36.

## 6. Applied

- [x] `ARCHITECTURE.md` updated to `1.8.2` (§12.5, §12.6, §25 OD-3), changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request (T-0021)
