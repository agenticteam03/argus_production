# T-0040 — `trace_request_path`: which hop of a container's dependency path is broken

| Field | Value |
|---|---|
| Status | `in progress` — #125 merged; on both VMs since the AFTER-MERGE to `main` `ad72617` (#132, 2026-10-13); next: offer to a class, with evaluation cases |
| Phase | 4 / 9 — Level 3, combined capabilities §12.7 ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change (no ACR): the §12 Level 3 row `analysis.trace_request_path` ("combined; follows the inventory dependency graph"), built on T-0034's mechanism |
| Branch | `task/T-0040-trace-request-path` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | after the merge only (the sub-reads need the executor tokens: verified from the worker, not a one-off container) |

## Design

- `analysis.trace_request_path` / `trace_request_path`: Level 3, combined (`max_subcalls` 9), in the worker, container
  targets, `max_per_incident` 1, tag `request_path` (offered to no class until measured).
- For each declared dependency (`depends_on` in the inventory) that is a container **on the same host**, at most 3:
  `container.status` (is it running), `network.connectivity` from the target to it (a shared Docker network), and
  `network.resolve_dns` (does its name resolve) — the stories of SC-03 (a stopped dependency) and SC-07 (the wrong
  network). Every sub-read goes through `InvokeCapability` (validation, policy, budget, audit, evidence) and is
  cited by its `evidence_id`.
- A dependency on another host, or a host target, is **listed as not traced**, never read from here (host isolation);
  more than 3 are listed as not traced.
- A failed hop is said (`not ok: …`, `partial`) and the trace goes on.
- **Not in it:** TCP to the dependency's port. A combined impl receives only the investigated target's inventory
  entry, not its dependencies' (`tcp_ports`); adding that would extend the §12.7 invoker contract (`read` only).

## Tests

`tests/test_t0040_trace_request_path.py`, 6 (red seen: no capability): spec and policy; the three sub-reads per hop
through `InvokeCapability` (caller, evidence, citations); a failed hop; no dependency; a host or another host's
container listed, never read; at most 3 traced.
