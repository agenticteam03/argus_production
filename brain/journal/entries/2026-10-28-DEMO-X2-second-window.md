## 2026-10-28 — DEMO-X2: second deployment window for the demo foundation

Type: deployment
Who: conantkd (+ agent, over SSH at conantkd's request)
Context: #354–#356 had merged; both VMs still ran `7f137da`; the first X-2 window had deployed phase 19 and the corpus.

Decision / result:
- Both leases were claimed under session `de222ef12a94`, and each VM's SESSION marker matched before the changes.
- Both VM checkouts advanced to the exact `main` commit `9798950bf6b0d7b3c26bd7699b39469d6e7ecdbc`.
- vm-095: a backup was created and verified (31 tables, 34,110 rows). The tunnel, agent, worker and scheduler were
  rebuilt. The internal `argus-v18-action` network contains the tunnel and worker only; no gateway alias resolves.
- vm-166: target services were rebuilt from the commit that adds `container_id` (the full Docker Id) to
  `container.status`. The action gateway and socket proxy were not started.
- `deploy.sh status` on both VMs reported the exact commit, clean checkouts and `LAB BASELINE OK`. The services
  remained running. No migration was added between `7f137da` and `9798950`.
- vm-095: 94/94 database checks passed; `WRITE GATE CLOSED` reported gate_open=0, write_capabilities=0 and
  action_gateway_resolves=0 for agent, worker and scheduler. vm-166's host-only check also reported
  `WRITE GATE CLOSED`. `nonint-check.sh after` reported `NO INTERFERENCE` on both VMs.

The first read-only probe ran vm-166's write-gate checker without `--host-only`, so it reported missing
agent/worker/scheduler containers. vm-166 is a target host with none of those services; the corrected host-only
check passed before and after deployment.

Consequences: X-2's closed-gate foundation is deployed. X-5 remains a separate release PR and deploy window; no
action token or active gateway configuration was installed here. Both leases were released after the record was
published.

References: [evidence](../../execution/history/DEMO-X2/step-01/evidence.md),
[coordination file](../../tasks/current/DEMO-argus-acts.md).

### Test state

Backup `VERIFY OK`; 94/94 database checks; gate closed on both hosts; both lab baselines OK; no interference on
both hosts. No code changed in this PR, so red/green and a local full suite do not apply. The exact `main` commit's
`main-guard` check succeeded; its `test` and `frontend` checks were skipped by the workflow. PR CI is pending.
No live action was attempted.

### Next step

X-5: after its release PR is reviewed, green and merged, use a separate leased window to provision the action token
and active gateway configuration, start the action services, then prove SC-03 end to end with human approval.
