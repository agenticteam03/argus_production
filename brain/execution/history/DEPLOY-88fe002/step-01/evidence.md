# DEPLOY-88fe002 step 01 — evidence: main 88fe002 on both VMs, operator console on (2026-10-30 UTC, conantkd)

Goal: put main `88fe002` (#399–#420: the operator console ACR-0043 with migrations 020–021, the approval that wakes a
paused run #419, the console audit fixes #416, the console guide #417, UI motion #420) on the VMs, with
`ARGUS_OPERATOR_CONSOLE=1`. vm-095 ran `a60e3f9`, vm-166 `bcccb5f` (no service on vm-166 changed since). Run by
conantkd's agent over ssh at conantkd's explicit request; both leases, session `31b8915f`, claimed 11:29Z.
conantkd chose to deploy while CI `main-guard` was red on main (#390, #392–#398 recorded by the open redemption PR
#400; #419 not yet recorded) and chose to turn the console on. Commands: [`code.bash`](code.bash). Sanitized: no
address, token or key.

| Block | Observed | Result |
|---|---|---|
| 1.1 vm-095 | marker; `commit=a60e3f9`, `ref=main`, `LAB BASELINE OK`; `NO INTERFERENCE`; `WRITE GATE AS RELEASED: 3 reviewed pair(s)` | OK |
| 1.2 vm-166 | marker; `commit=bcccb5f`; `LAB BASELINE NOT OK: argus-lab-client` (exited 137 about 40 h before, see note 3); `NO INTERFERENCE`; `WRITE GATE AS RELEASED: 3 reviewed pair(s); host-only` | OK |
| 2.1 vm-166 | `before` saved (63 lines); `DEPLOY OK: 88fe00223023`; `WRITE GATE AS RELEASED`; `NO INTERFERENCE` | OK |
| 2.2 vm-095 | `before` saved (54 lines); backup `argus-20261030T113052Z.dump` (3267230 bytes); `DEPLOY OK` (`deployed_at=2026-10-30T11:31:19Z`); `schema_migrations` ends `020_console_command`, `021_console_analysis`; `ARGUS_OPERATOR_CONSOLE=1` once in `hosts.env` and `deploy/ui/vm-095.env` (copies `*.pre-88fe002`); agent, worker, scheduler recreated 11:33:46Z from one image built 11:32:37Z; UI recreated 11:34:19Z, healthy; `nginx -t` successful; agent `ARGUS_OPERATOR_CONSOLE=1` | OK, see note 1 |
| 2.3 vm-095 | **`VERIFY OK: 31 tables, 43543 rows match`**; agent health 200; the UI bundle calls `ops/console`; the agent's OpenAPI lists 6 `/ops/console/` routes (404 off the private path, as designed); error lines since the restart: 0 in agent, worker, scheduler and UI (the raw count matched the metric name `argus_probe_error` in successful queries); **`WRITE GATE AS RELEASED`**; **`NO INTERFERENCE`** | OK |

## Notes

1. **2.2's output was captured only up to its first line.** The laptop's ssh session for the block ended early (a
   background-run problem on the laptop); the remote script kept running to its end, observed with `pgrep` on
   vm-095. Every result of 2.2 above was read afterwards from the VM's state, and its read-only checks were re-run as
   2.3 (the backup verify included).
2. **Lease and marker.** A first probe (1.1/1.2) ran at 11:12Z before the lease was claimed: `brain.py start` had not
   finished and the agent acted on a notification it had not checked against the `session` branch. That probe was
   read-only apart from writing `/opt/argus-v18/SESSION` with an id that was never claimed; nobody held a lease
   (the last one was conantkd's, released). The claim then failed twice: the pre-push hook needs `pre-commit`, and
   this laptop's `.venv` points at another user's Python; `pre-commit` was installed as a uv tool and the claim
   went through (`start` with `BRAIN_NO_GH=1`: its `verify-main` took over 10 minutes; CI's `main-guard` gave the
   same result). The probe was re-run with the claimed id before any change.
3. **`argus-lab-client` on vm-166 is stopped** (exit 137, about 40 h before this window), so its lab baseline is not
   OK. This deploy did not touch it; restore it before the next scenario test.
4. The write gate stays as released (3 reviewed pairs, the demo's state); `config/policy.yaml` did not change
   (policy `4a198cd15d21`). The only action-card change, `network.restore`'s `rollback` text, does not alter a pair.
5. Undo, if needed: put back the two `*.pre-88fe002` env files, `deploy.sh a60e3f9…` on vm-095 and rebuild the same
   four services; `deploy.sh bcccb5f…` on vm-166. Migrations 020–021 stay (additive; `a60e3f9` never reads them).
