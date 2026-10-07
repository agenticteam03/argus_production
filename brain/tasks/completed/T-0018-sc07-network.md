# T-0018 — SC-07: a healthy backend on the wrong network

| Field | Value |
|---|---|
| Status | `verified` on vm-166 (2026-10-07); merged by this pull request |
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

- **Branch runbooks through `knowledge.runbook` (2026-10-07, after the first SC-07 run):** RB-009 was not recalled,
  because recall is one TF-IDF search at the start and the architecture's way to reach a branch runbook later
  (§3: "retrieved when the investigation points to that cause"; §10.5: "a strategy may request more through the
  in-worker capabilities `knowledge.runbook`") was not implemented. `conantkd` chose the general mechanism over a
  per-case class (`dns_network_failure`), so every class with branches benefits, and the per-class detectors can
  be enabled later once their runbooks are tested (§3 "Enablement"). No orchestration flow changes: a capability
  (`query_runbook`, executor `argus_internal`, `runs_in="worker"`), its policy limit (3 per incident), and one
  context line that names the class's branch runbooks.

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
7. **`knowledge.runbook`** (tests first), deploy the agent on vm-095, run SC-07 again: RB-009 is tested only if
   the model actually reads it.
6. **Brain and PR:** plan (SC-07 ✅, host vm-166), `docs/INCIDENTS.md`, RB-009 `last_tested`, journal; PR with the
   teammates tagged about the network rule.

## Red seen / evidence

- **2026-10-06 — step 2 (code, tests first):**
  - **red:** `tests/test_sc07_network.py` 5 of 5 failed for the right reasons (`KeyError: 'networks'` ×2, no
    `networks=` in the capability text, no client→backend probe in `vm-166.json`, no `sc07` profile); then the
    probe-gating test failed (`no attribute 'probe_lines'`);
  - **green:** 6/6; full offline suite 95 passed, 6 skipped (101).
- **2026-10-06 — step 1 (vm-166, read-only):** `SUBNET FREE: 172.30.3.0/24` (non-Argus networks use
  `172.17`–`172.21`); NO INTERFERENCE. [Evidence](../../execution/history/T-0018/step-01/evidence.md).
- **2026-10-07 — step 4 (deploy, `df267ce`):** vm-166 target services rebuilt (the gateway answers
  `networks=['argus-lab-app']`), vm-095 agent rebuilt (sees the SC-07 targets), H-1 on vm-166's api `HEALTHY`,
  NO INTERFERENCE on both. [Evidence](../../execution/history/T-0018/step-04/evidence.md).
- **2026-10-07 — step 5 (SC-07 on vm-166):** `inc_fb92d115abb2` **DIAGNOSED**, `dependency_unavailable`, root cause
  `vm-166/container:argus-lab-backend`, confidence high: *"not attached to the client's application network … the
  client is on argus-lab-app while the backend is only on argus-lab-iso … do not restart containers"*. Reset done,
  LAB BASELINE OK, NO INTERFERENCE. RB-009 was **not** recalled (branch runbook): its `last_tested` stays `null`
  (follow-up). [Evidence](../../execution/history/T-0018/step-05/evidence.md).
- **2026-10-07 — step 7 (code, tests first): `knowledge.runbook`:**
  - **red:** `tests/test_knowledge_runbook.py` 5 of 5 failed (the capability did not exist: `refused`);
  - then 2 failures that taught something: the full sha256 of a passage was masked by the redactor as a
    high-entropy secret (the redactor is right; the capability now returns a 16-character prefix, like the recall
    timeline), and the test's own first-step condition was wrong (detect already stores evidence);
  - **green:** 5/5; full offline suite 100 passed, 6 skipped (106).
- **2026-10-07 — step 7 on the VMs (agent `68d4963`, SC-07 run 2):** `inc_21f900ee6139` DIAGNOSED; after the TCP
  probe failed the model called **`query_runbook` → RB-009** (3 sections) and then checked name resolution first, as
  RB-009 prescribes; "do not restart the backend". Root-cause target the host (less precise than run 1, still
  correct). RB-009: `last_tested: 2026-10-07` (the run read version 1.0.0; metadata bumped to 1.0.1 for `last_tested`), still `draft` (promotion needs more cases and a
  reviewer). [Evidence](../../execution/history/T-0018/step-07/evidence.md).
- **2026-10-07 — RB-009 adapted to 1.1.0 (`conantkd`):** run 2 stopped at "name resolution" because RB-009's decision
  tree sent a DNS failure straight to "resolver/record" and its step 3 named a tool that does not exist
  (`get_container_network`). Now: on Docker, a name that does not resolve first leads to comparing the `networks`
  of source and destination (no shared network → wrong attachment, name both networks, no restart); the tool table
  points to `get_container_status` → `networks`; the lab-validation section records SC-07. Not run yet with 1.1.0.
- **2026-10-07 — SC-07 run 3 and the analysis (`conantkd`):** run 3 (`inc_dbd9ba0253a7`) did not read RB-009 nor any
  container status. The stored evidence of the three runs shows the precise diagnosis (run 1) came only when the
  model happened to read the status of **both** sides; the tool description did not say it returns networks.
  Of the suggestions (network-named probe text, tool description, RB-003 step 2, detector finding naming the edge
  and layer, "Decide now"), `conantkd` chose only the tool description.
  - **red:** `test_container_status_tool_tells_the_model_it_returns_networks` (`'network' in 'container state, …'`);
  - **green:** the description names the attached Docker networks and the use-when says to compare a victim's and
    its dependency's networks when a name does not resolve; full suite 101 passed, 6 skipped (107).
