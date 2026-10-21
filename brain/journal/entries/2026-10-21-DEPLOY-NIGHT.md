## 2026-10-21 — DEPLOY-NIGHT: vm-095 to main 024aa6f (migration 009); OP-004 and OP-008 previewed

Type: deployment
Who: conantkd (+ agent, unattended night session, over ssh)
Context: main gained migration 009 `link_event` (#220), T-0046 L1 (#219) and #221 since DEPLOY-215.
Decision / result: vm-095 runs `main` `024aa6f`; `+ 009_link_event applied`; agent, worker and scheduler on one
image; 29/29 database checks, 55/55, write gate closed, `NO INTERFERENCE` on both VMs; the deploy event recorded once
(the manual `argus deploy record` is gone from the code.bash). vm-166 stays on `bdcd048`. Previews only: OP-004 finds
no checkpoint past 30 days; OP-008 would remove 13 backup sets, none removed (a deletion is a stop condition).
Evidence: [DEPLOY-NIGHT](../../execution/history/DEPLOY-NIGHT/step-01/evidence.md).
Consequences: OP-004 and OP-008 wait only for the team's decision on their timers; the backup prune is conantkd's call.
References: #219, #220, #221, OP-004, OP-008.
