# T-0031 step 03 — evidence: the write gate on the Host T (vm-166) and again on vm-095 (2026-10-10, conantkd, session 9c71a9bf260a)

Run by the agent over SSH with both leases (`code.bash` in this folder). The branch's `ops/` and `argus/` were copied
to `/tmp/argus-t0031` with `git archive` and removed afterwards; both VMs stayed on the deployed `main` `ebbe9c9`.
Read-only. Sanitized: no addresses, no secrets (names only).

| Check | Result |
|---|---|
| W.1 vm-166 state | 21:08:55 UTC; session marker mine; `ref=main` `ebbe9c9`; LAB BASELINE OK |
| W.1 vm-166 containers | 9 `argus-v18-*`: prometheus, host-probe, read-gateway, exporter, network-probe, db-probe, node-exporter, cadvisor, alertmanager; none named like an action gateway |
| W.1 vm-166 secrets/ | `db_probe_token`, `deploy`, `docker_read_token`, `host_probe_token`, `lab-db`, `network_probe_token`, `prometheus`: read tokens only, nothing named like an action credential |
| W.1 `write-gate-check.sh --host-only` | **`WRITE GATE CLOSED: host-only (no Argus service here); no action gateway, mount or credential`**, exit 0; NO INTERFERENCE |
| W.2 vm-095 state | 21:09:09 UTC; session marker mine; `ref=main` `ebbe9c9`; LAB BASELINE OK; 13 `argus-v18-*` containers inspected |
| W.2 `write-gate-check.sh` | agent, worker, scheduler: `gate_open=0 write_capabilities=0 action_gateway_resolves=0 policy=987032aaddc8` (the hash `/healthz` reports); **`WRITE GATE CLOSED`**, exit 0; NO INTERFERENCE |
| Re-run with the final script | Second review found the host-only mode failed open when `docker ps` fails (empty list, no service to fail → CLOSED). Fixed (a failed `docker ps` is now a STOP reason) and both checks re-run with that script at 21:20 UTC: vm-166 `--host-only` **WRITE GATE CLOSED**, vm-095 **WRITE GATE CLOSED**; NO INTERFERENCE on both |

**Result:** nothing on either host can write. On vm-166, where ARCHITECTURE §2 would place the action gateway, there
is no action container, no action mount or variable on any Argus container, and no action credential on disk. On
vm-095 the extended check (every Argus container, `secrets/`) still reports the gate closed in all three services.
