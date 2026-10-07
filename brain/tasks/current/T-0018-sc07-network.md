# T-0018 — SC-07: a healthy backend on the wrong network

| Field | Value |
|---|---|
| Status | `in progress` — started 2026-10-06; step 2 done, step 1 (vm-166 probe) waiting for its output |
| Phase | 11 — synthetic incidents ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) §7, SC-07) |
| Architecture | no change (no ACR): lab workloads, one more read-only field, one more Argus lab network |
| Branch | `task/T-0018-sc07-network` |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | steps 1, 4 and 5 (vm-166 only) |

## Goal (plain language)

A client cannot reach its backend, although the backend is running and healthy: they sit on **different Docker
networks**, so Docker's DNS on the client's network does not know the backend's name. Argus must diagnose a
**network misconfiguration, not a failed service** (RB-009), on vm-166, through the tunnel like every Host T
incident. Restarting the backend would fix nothing; a good diagnosis says which networks each side is on.

## Decisions (2026-10-06, `conantkd`)

- **Host: vm-166** (Host T, the lab host), not vm-095 as the plan first said: breaking a network next to the agent
  is riskier, and the scenario then also exercises the cross-host path. The plan and `docs/INCIDENTS.md` follow.
- **Option b: a second lab network `argus-lab-iso`** (`172.30.3.0/24`) instead of a backend with no network at
  all. It is the realistic mistake (two compose projects, two networks). It widens the Argus network rule from
  `172.30.0–2.0/24` to `172.30.0–3.0/24`: `infrastructure/environment.md`, `IMPLEMENTATION_PLAN.md` and
  `agents/AGENT_PROTOCOL.md` §7 change in this PR, and the teammates are tagged in it. No ACR: the architecture
  names no subnets and no safety principle changes.
- **The probes stay on `argus-lab-app`**, the client's network: they see what the client sees (RB-009: a probe
  elsewhere proves nothing about the client's path).
- **Dependency probes only while their owner runs** (found while designing): the client→backend probe is declared
  permanently, so outside SC-07 it would report 0 and keep `DependencyProbeFailed` firing on vm-166. The exporter
  now skips the probes of owners that are not running (SC-03 is unchanged: its owner, the api, keeps running).

## Design

- **Lab (profile `sc07`, `deploy/lab/compose.lab.yml`):** `argus-lab-backend` (the lab api, standalone, healthy)
  only on `argus-lab-iso`; `argus-lab-client` on `argus-lab-app`, calling `http://argus-lab-backend:8080/health`
  every few seconds and logging each failure. `argus-lab-iso` is created and removed with the profile.
- **Inventory (vm-166):** `argus-lab-client` depends on `argus-lab-backend` (TCP 8080), so the exporter's
  dependency probe fails and the existing class `dependency_unavailable` fires (RB-009 is already its branch).
- **Read gateway:** the container `status` gains `networks` (the names of the attached Docker networks; read-only,
  no addresses), and the `container_status` capability shows it to the model.
- **Expected outcome:** `DIAGNOSED`: the backend is healthy but attached only to `argus-lab-iso`, the client only
  to `argus-lab-app`; root cause a network misattachment (RB-009), not a failed service.
- **Not in scope:** a dedicated `dns_network_failure` class and detector (later, if the dependency path proves too
  weak); any change on vm-095.

## Steps

1. **Probe vm-166 (read-only):** deployed commit, lab baseline, every Docker network with its subnet, the host's
   IPv4 routes and addresses; verdict whether `172.30.3.0/24` is free. NO INTERFERENCE.
2. **Tests first, then code:** `networks` in the gateway status and in the capability text; the inventory renders
   the client→backend probe on vm-166.
3. **Lab and rules:** the `sc07` profile, the `argus-lab-iso` network, the client workload; the network rule in the
   Brain widened to `0–3`.
4. **Deploy on vm-166:** checkout of this branch, rebuild the target services (the new field), NO INTERFERENCE.
5. **Run SC-07:** induce → wait for the probe signal → diagnose → verify → reset → NO INTERFERENCE; evidence.
6. **Brain and PR:** plan (SC-07 ✅, host vm-166), `docs/INCIDENTS.md`, RB-009 `last_tested`, journal; PR with the
   teammates tagged about the network rule.

## Red seen / evidence

- **2026-10-06 — step 2 (code, tests first):**
  - **red:** `tests/test_sc07_network.py` 5 of 5 failed for the right reasons (`KeyError: 'networks'` ×2, no
    `networks=` in the capability text, no client→backend probe in `vm-166.json`, no `sc07` profile); then the
    probe-gating test failed (`no attribute 'probe_lines'`);
  - **green:** 6/6; full offline suite 95 passed, 6 skipped (101).
