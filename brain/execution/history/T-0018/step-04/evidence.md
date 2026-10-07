# T-0018 step 04 — evidence (2026-10-07 04:55–05:05 UTC, run by the agent over SSH for conantkd, session 796fd4f3bf61)

Goal: deploy the SC-07 code on both VMs (no scenario yet): the target services on vm-166 return `networks` and
probe a dependency only while its owner runs; the agent on vm-095 reads the SC-07 targets and shows `networks`.

The blocks of `code.bash` (this folder) were run by the agent over SSH at `conantkd`'s request ("run the
verification steps and keep the output"), except the H-1 check, which needs the user's Argus password.
Key output lines, SANITIZED (no VM addresses, no secrets, no personal names). The gateway token was used inside
its own container and never printed.

| Block | Expected | Observed | Result |
|---|---|---|---|
| T.1 vm-166 session + before | `SESSION OK`, snapshot | `SESSION OK`; `saved … before.txt (87 lines)` | OK |
| T.1 checkout | `DEPLOY OK (task/T-0018-sc07-network)` | `DEPLOY OK: df267cea20af (task/T-0018-sc07-network) on argus-vm166` | OK |
| T.1 rebuild | the 4 target services Up, lab untouched | `argus-v18-read-gateway`, `-host-probe`, `-network-probe`, `-exporter` Up 15–17 s; `argus-lab-api Up 24 hours (healthy)`, `argus-lab-cache Up 23 hours`, `argus-v18-prometheus Up 24 hours` | OK |
| T.1 status + after | `ref=task/T-0018-sc07-network`, `LAB BASELINE OK`, NO INTERFERENCE | `commit=df267cea20af…`, `ref=task/T-0018-sc07-network`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged` | OK |
| gateway check vm-166 | the status carries `networks` (names only) | `argus-lab-api state=running health=healthy networks=['argus-lab-app'] host=vm-166`; `argus-lab-cache … networks=['argus-lab-app']`; no address in the answer | OK |
| T.2 vm-095 session + before | `SESSION OK`, snapshot | `SESSION OK`; `saved … before.txt (69 lines)`; agent `Up 18 hours`, postgres `Up 24 hours (healthy)` | OK |
| T.2 checkout | `DEPLOY OK (task/T-0018-sc07-network)` | `DEPLOY OK: df267cea20af (task/T-0018-sc07-network) on argus-vm095` | OK |
| T.2 agent rebuild | agent recreated, health 200, postgres untouched | `argus-v18-agent Recreated … Started`; `health 000` then `health 200`; agent `Up 5 seconds`, postgres `Up 24 hours (healthy)` | OK |
| T.2 agent content | new capability text; SC-07 targets loaded | `agent image has networks text: True`; `agent sees SC-07 targets: ['vm-166/container:argus-lab-client', 'vm-166/container:argus-lab-backend']` | OK |
| T.2 status + after | `ref=task/T-0018-sc07-network`, `LAB BASELINE OK`, NO INTERFERENCE | `commit=df267cea20af…`, `ref=task/T-0018-sc07-network`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged` | OK |
| T.2 H-1 on vm-166's api (run by `conantkd`, password prompted) | outcome `HEALTHY` | `incident inc_117167cc3354`; `outcome: HEALTHY — nothing to do` | OK |

nonint-check: NO INTERFERENCE on vm-166 (yes) and vm-095 (yes).

Notes:
- The vm-095 agent image now also carries T-0015 (already on `main`): T-0015 step 6 no longer needs a rebuild,
  only its proof that a read token is refused on `POST`.
- `deploy.sh` on vm-095 also hinted the target services (their code changed); not rebuilt there, because SC-07
  runs on vm-166 and vm-095 declares no dependency probe (its services behave the same).
