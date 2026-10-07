# OP-007 step 01 — evidence (2026-10-07, conantkd, session 3307114120d3)

Goal: run the target services on vm-166 with `owner_active` (a dependency probe stays published while its owner is
running or restarting). Block O.1 was run by the agent over SSH; nothing needed a password.

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

| Check | Expected | Observed | Result |
|---|---|---|---|
| Session | `SESSION OK` | `SESSION OK` | OK |
| Checkout | `DEPLOY OK` on the branch head | `DEPLOY OK: 9c04e90ecf43 (task/op-007-restarting-probe-fix) on argus-vm166`; `ref=task/op-007-restarting-probe-fix` | OK |
| Rebuild | 4 target services recreated, lab untouched | exporter, host-probe, network-probe, read-gateway `Up ~30 seconds`; `argus-lab-api Up 35 hours (healthy)`, `argus-lab-cache Up 34 hours`, prometheus `Up 35 hours` | OK |
| New code in the image | `owner_active` present | 3 occurrences in `/app/service.py` of `argus-v18-exporter` | OK |
| Healthy owner keeps its probe | api -> cache = 1 | `argus_probe_success{owner="argus-lab-api"} = 1` | OK |
| SC-07 false alarm stays fixed | no series for the absent client | `count(argus_probe_success{owner="argus-lab-client"}) or vector(0) = 0` | OK |
| Lab and isolation | `LAB BASELINE OK`; NO INTERFERENCE | `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged` | OK |

nonint-check: NO INTERFERENCE on vm-166 (yes). vm-095 not touched.

**Result:** vm-166 runs `task/op-007-restarting-probe-fix` `9c04e90`. The restarting-owner case itself is covered by
`test_exporter_keeps_the_probe_of_an_owner_in_a_restart_loop`; a live crash loop was not provoked (it would need
breaking `argus-lab-cache`, which is a scenario, not a deploy check). After the merge, vm-166 goes back to `main`
(checkout only: the same code).
