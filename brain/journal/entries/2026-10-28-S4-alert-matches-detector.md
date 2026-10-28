## 2026-10-28 - S4: the WorkerStalled alert waits for the detector's own zero processed rate

Type: fix
Who: conantkd (+ agent)
Context: the first S4 rehearsal on vm-166 (main `e92052f`, both pairs released, leases session `b2e332b56b27`) froze
the lab job worker at 10:30:37Z. `WorkerStalled` fired at 10:33:46Z (last progress older than 180 s, queue above 10
and growing) and opened `inc_69562bea2e28` at 10:34:49Z. The `worker_stalled` detector also needs a zero 5-minute
processed rate (`config/signals.yaml`), which was still positive, so no class matched and the incident escalated as
`unsupported_escalated` without a diagnosis or a proposal.
Decision / result: `deploy/monitoring/alerts.yml` adds the detector's condition to the alert,
`rate(argus_lab_jobs_processed_total{job="argus-lab-jobworker"}[5m]) == 0`, joined on `argus_host` and `container`
like the other terms. The alert now fires no earlier than the class can match. `promtool check rules` passes on
vm-166's Prometheus (v3), and the live series carries both join labels.
Consequences: the window reloads vm-166's Prometheus rules after this merges and repeats the S4 rehearsal.
References: [demo plan](../../tasks/current/DEMO-argus-acts.md), RB-022.

### Test state

`tests/test_s4_class.py` asserts the alert contains the zero rate over the detector's own window, read from
`config/signals.yaml`; it fails on the old rule and passes with the new one. The whole file passes locally; CI is the
full check.

### Next step

Merge, recreate vm-166's Prometheus, and rerun S4 up to the pending approval.
