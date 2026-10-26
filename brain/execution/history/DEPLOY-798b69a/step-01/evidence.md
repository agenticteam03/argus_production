# DEPLOY-798b69a step 01 — evidence: vm-095 to main 798b69a, security alerts to Telegram and the egress proxy (2026-10-26 UTC, conantkd)

Goal: run on vm-095 phase 16's last two pieces (#344): security events posted by the scheduler to vm-095's
Alertmanager and sent to the team's Telegram group through `argus-v18-egress`; the scheduler on the internal network
`argus-v18-sched`, leaving only through the proxy (OCI Object Storage and the Telegram API). No migration (schema
001-016), no UI or contract change; vm-166 does not change. Run by conantkd's agent over ssh at conantkd's request,
both leases (session `3d07ee84`); D.3 run by conantkd. Commands: [`code.bash`](code.bash). Sanitized: no address,
token or chat id.

| Block | Observed | Result |
|---|---|---|
| D.1 vm-166 | marker; `before` saved (63 lines) | OK |
| D.2 vm-095 | `ref=6e87828`, `LAB BASELINE OK`; `before` saved (54 lines); evaluations running: 0; `BACKUP OK` (2540185 bytes, 17:08Z); **`VERIFY OK: 31 tables, 33797 rows match`**; `DEPLOY OK: 798b69a73ca7 (798b69a)` | OK |
| D.3 vm-095 | token file present (reused, written earlier by conantkd); `Telegram API: ok`; **groups seen: 1** (the team's group); both files `-r--------` owned by `nobody` | OK |
| D.4 vm-095 | **`Network argus-v18-sched Created`**; `argus-v18-egress` built and `Started`; tunnel, postgres, agent, scheduler, worker `Recreated`, `Started`; `health 200`; **`sched internal: true`**; **scheduler networks: `argus-v18-sched` only**; `deploy recorded: 798b69a (main) on vm-095 by conantkd` | OK |
| D.5 vm-095 | prometheus and alertmanager `Recreated`, `Started`, `running restarts=0`; alertmanager error/warn lines: 0 | OK |
| D.6 vm-095 | agent, worker, scheduler, egress, UI `running restarts=0`; **via proxy: `api.telegram.org` reached, `github.com` and `api.openai.com` refused (`ProxyError`); direct: refused (`ConnectError`)**; egress `filtered` lines: 2; **test alert posted 200, notify failures 0; the message reached the team's Telegram group** (seen by conantkd, 17:24Z); agent and worker error lines 0, scheduler 8 (note 1); `security alerts: 0 security alert(s)` every minute; **`91/91 database checks passed`**; `AUDIT CHAIN OK: 327 rows chained`; public `/api/v1/ops/` printed `000` (note 2), re-read **404**, `/api/v1/ops/approvals/x` 404, `/api/v1/me` 401; `ref=798b69a`, `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.7 vm-166 | `NO INTERFERENCE` | OK |

## Notes

1. **The scheduler's 8 error lines** are `alerts of vm-095 not read: ConnectError`, 17:12 to 17:23:45Z: from D.4 the
   scheduler was on `argus-v18-sched` alone, and vm-095's Alertmanager joined that network only in D.5 (started
   17:23:59Z) — about 12 minutes while D.3 waited for the developer. From then on the reads succeed. In that window
   the heartbeat raised one `monitoring lost` escalation for vm-095 (17:17Z), resolved by the next ticks. Next time
   run D.5 straight after D.4 (or the secret files first).
2. **`public ops: 000`** was the block's error: `ARGUS_UI_DOMAIN` is in `deploy/ui/vm-095.env`, not `hosts.env`. The
   archived block has the corrected line; the re-read answered 404.
3. The D.3 script copied to the developer's home on vm-095 was removed after the run.
4. **Rollback:** in the header of [`code.bash`](code.bash) (`deploy.sh 6e87828`, the core compose, remove
   `argus-v18-egress`, the monitoring compose, remove `argus-v18-sched`).
