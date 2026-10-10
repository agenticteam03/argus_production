# T-0031 — Phase 8: the standing write-gate test

| Field | Value |
|---|---|
| Status | `done` 2026-10-10 (standing test in every build; `WRITE GATE CLOSED` on vm-095 and, host-only, on vm-166) |
| Phase | 8 — policies ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "standing write-gate test on the VMs") |
| Architecture | no change (§22.2 standing test, §13.3 write gate, §13.4 required behaviours) |
| Branch | `task/T-0031-write-gate-standing`, from `main` |
| Owner | `conantkd` (+ agent) |

## Goal (plain language)

Argus is read-only in this release. §22.2 asks for a test that proves it in every build while nothing is released,
and for a deployment check that nothing on the agent host could write even if the code tried.

## What was built

- **Standing test** (`tests/test_write_gate_standing.py`, runs in CI on every push): a model reply proposing
  `container.restart` four ways (the capability name, `restart_container`, a `propose_remediation` tool, and a
  restart hidden behind a legitimate read) on both runners ends `no_action_escalated`, audits
  `security.fabricated_tool`, creates no approval or write node, sends no non-GET request and no restart/action path,
  and in the mixed reply executes not even the read. The catalogue holds only read safety classes; the policy file's
  `write_gate.open` is empty and the engine refuses a non-empty one.
- **Deployment check** (`ops/write-gate-check.sh` + `argus/infrastructure/gate_report.py`, read-only): no container named like
  an action gateway; in the agent, worker and scheduler, the loaded policy's gate is empty, the catalogue has no write
  capability and `argus-v18-action-gateway` does not resolve; no action mount or `ARGUS_ACTION*` variable (names only).
  The report's source is fed to the container's python on stdin, so it checks the running image even if it predates
  the module.

Note: §12 lists `container.restart` as "registered; not released"; the code does not register it at all, which is
stricter. When a write capability is built, this test is the one that must keep passing until its §22.2 release.

## Steps

1. **Code and tests** (done): 10 standing cases + 9 check cases. The standing cases passed at once (they pin existing
   behaviour), so red was seen by mutation: an engine that accepts an open gate, a harness that accepts a tool it did
   not offer (all 8 proposal cases red), a capability registered as `MUTATING_LOW_RISK`. The check's cases were red
   before the module and the script existed.
2. **vm-095** (done, [evidence](../../execution/history/T-0031/step-02/evidence.md)): `WRITE GATE CLOSED` on `main`
   `ebbe9c9`; NO INTERFERENCE.
3. **vm-166** (done, [evidence](../../execution/history/T-0031/step-03/evidence.md)): §2 places the action gateway on each Host T, so the
   host where it must be absent is above all vm-166, which step 2 did not check. `write-gate-check.sh --host-only`
   skips the service reports (a Host T runs no Argus service). Both modes now inspect every `argus-v18-*`
   container for action mounts and variables, not only the three services, and stop on a file under `secrets/`
   named like an action credential. 6 new check cases, red seen before the change. With both leases: vm-166
   `--host-only` → `WRITE GATE CLOSED` (9 Argus containers, read tokens only in `secrets/`); vm-095 full check again
   → `WRITE GATE CLOSED` (agent, worker, scheduler `gate_open=0 write_capabilities=0 action_gateway_resolves=0`, 13
   containers inspected); NO INTERFERENCE on both.

## Not covered

The action gateway does not exist yet, so "unreachable from Host A" is checked as "absent and unresolvable". When it
is built, the check must also prove its firewall rule closed and its port not listening while nothing is released
(today it has no port to look for).
