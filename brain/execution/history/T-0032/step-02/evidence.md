# T-0032 step 02 — evidence: Prometheus down on vm-095, a partition of that host only (2026-10-10, conantkd, session ecee514c2421)

`code.bash` in this folder. P.0 and P.1 ran by the agent over SSH; conantkd then ran P.0 to P.5 in one shell (the
second `docker stop` found Prometheus already stopped). Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| P.0 state | vm-095 on `main` `ebbe9c9`; LAB BASELINE OK; Prometheus, agent, worker, scheduler running, **restarts=0**; no active alert in Alertmanager |
| P.1 outage | `docker stop argus-v18-prometheus` at 16:25:27 UTC → `exited` |
| P.2 vm-095 | `inc_4e684ad1a6c0`: `metrics stale or unavailable: prometheus at http://argus-v18-prometheus:9090: ConnectError` → **UNDIAGNOSABLE → escalated (metrics missing)**; no model call |
| P.2 vm-166 | `inc_4e3c53feb2f5`: **HEALTHY — nothing to do** (read through vm-166's Prometheus over the tunnel while vm-095's was down) |
| P.3 services | agent, worker, scheduler **restarts=0**, all running; no error or traceback in the worker or scheduler logs (the one matching line is a successful query whose metric name contains `gateway_error`); `/healthz` `{"ok":true,…}` |
| P.4 back | `docker start` → `/-/ready` at 16:27:39 (outage about 2 min 12 s); after one scrape interval `count(up==0)` empty, the exporter's `up` = 1; no active alert; LAB BASELINE OK; **NO INTERFERENCE** |
| P.5 vm-095 | `inc_6d934b947ef2`: **HEALTHY — nothing to do** |

Note: conantkd's second run of P.0 saved the `before` baseline again during the outage. The non-interference check
compares non-Argus objects only, so a stopped Argus Prometheus does not change it.

**Result:** with vm-095's Prometheus down, a vm-095 check is escalated as UNDIAGNOSABLE before any model call (unknown
is never healthy), a vm-166 check still answers HEALTHY, no Argus container restarts, and the vm-095 check is HEALTHY
again as soon as Prometheus is back.

**Seen, not fixed (follow-up):** during the outage no alert can fire for it, because `ArgusScrapeTargetDown` is
evaluated by the same Prometheus that is down. Only a check (or the Argus UI) shows it.
