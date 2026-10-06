# LAB-BASELINE step 01 — evidence (2026-10-06, conantkd, session 6b413ecc1488)

`ops/deploy.sh status` now reports whether the lab is at its baseline. Deployed as `task/lab-baseline-check`
`58a51c3` on both VMs (only `ops/deploy.sh` changed since `09f5ab1`: no container rebuilt).

| VM | nonint before | DEPLOY | status lab lines | verdict | nonint after |
|---|---|---|---|---|---|
| vm-166 | saved (87 lines) | `DEPLOY OK: 58a51c3ad64f (task/lab-baseline-check)`, no rebuild hints | `argus-lab-cache running Up 27 minutes`, `argus-lab-api running Up About an hour (healthy)` | `LAB BASELINE OK` | NO INTERFERENCE |
| vm-095 | saved (69 lines) | `DEPLOY OK: 58a51c3ad64f (task/lab-baseline-check)`, no rebuild hints | `argus-lab-api running Up About an hour (healthy)` | `LAB BASELINE OK` | NO INTERFERENCE |

The NOT OK path (a stopped or unhealthy lab container) is covered by `tests/test_deploy.py` with the exact lines
observed in DEPLOY-MAIN D.3b-1; it will also show on the VMs during the next scenario that stops a lab container.

Commands (per VM): `nonint-check.sh before` → `deploy.sh task/lab-baseline-check --as conantkd` → `deploy.sh status`
→ `nonint-check.sh after`. Undo: `deploy.sh main --as <you>` (same containers, nothing to rebuild).
