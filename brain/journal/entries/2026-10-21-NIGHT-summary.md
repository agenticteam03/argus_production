## 2026-10-21 — Unattended night session: what merged, what waits, what was found

Type: summary
Who: conantkd's agent, unattended (22:45 to 04:00 local, UTC-5), at conantkd's request: "avanzar en las fases de
implementación… pocos PR… al final sacar todos los que se puedan via selfmerge… correr una última vez todo".
Context: the plan was four pull requests (small fixes, ACR-0028 applied, phase 16 step 1, the night's records), a
deploy of main, and a final check of main, the VMs and #210.
Decision / result:
- **Reviewed and merged first (asked):** #220 (T-0046 L2, `link_event`, migration 009), conantkd's approval.
- **Self-merged:** #221 (one link per dependency; `host.read_file` raised `TypeError` on every successful read, found
  by the ACR-0028 canary test); this records pull request.
- **Deployed:** vm-095 to `024aa6f` with migration 009 ([DEPLOY-NIGHT](../../execution/history/DEPLOY-NIGHT/step-01/evidence.md)):
  29/29 database checks, 55/55, write gate closed, `NO INTERFERENCE` on both VMs. OP-004 and OP-008 previewed only
  (13 backup sets would be pruned; nothing deleted: a stop condition).
- **Waiting for a teammate (protected paths):** #222 (ACR-0028 applied, 1.8.25), #223 (phase 16 step 1: sessions,
  revocation, persisted login limiter, permissions, the audit hash chain with a scheduled check, EdDSA; 1.8.26,
  migrations 010 and 011), #210 (ACR-0026: approved on an earlier push; a hand-resolved merge needs a re-approval).
- **Found and fixed on the way:** a key-like literal in a database check tripped gitleaks on every PR's CI (the scan
  covers all fetched branches), replaced by `md5('dbcheck')`; two existing UI tests followed the intended changes.
  **A mistake of mine, caught before any merge:** squashing #223 with `git reset --soft origin/main` after #221 had
  merged made its single commit revert #221 (the read_file fix, its tests, its journal); restored, and every PR's
  diff against main re-checked file by file.
  A flaky property test on main (`test_op014_property_based`: a URL user named `passwd` is masked by the key rule,
  in another form; no leak) failed #223's CI once; fixed in #223.
- **Not done, and why:** the `compare_baseline` evaluation for `container_restart_loop` (T-0047; needs constructed
  earlier-window fixtures and OpenAI spend not approved for tonight); phase 16 steps 3 to 5 (WebAuthn needs a library
  choice and the UI; the private path, the off-host store and the alert receiver need team decisions). The plan for
  them is [PHASE-16](../../tasks/current/PHASE-16-operator-access.md).
Consequences: next for conantkd: approvals of #222 / #223 / #210 from `juanbetancurm`; then the prepared deploy of
phase 16 step 1 ([code.bash](../../execution/history/PHASE-16/step-01/code.bash)); the backup prune is conantkd's call.
References: #210, #220, #221, #222, #223, ACR-0018, ACR-0028, OP-004, OP-008.
