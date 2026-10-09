# T-0022 — Phase 7: alerting (Argus-owned exporters and Alertmanager; alerts pulled through the transport profile)

| Field | Value |
|---|---|
| Status | `in progress` — 2026-10-08 (steps 1-4 done; step 5 waits for #36) |
| Phase | 7 — monitoring & detection ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "Alertmanager, node-exporter, cAdvisor; pull firing alerts") |
| Architecture | **ACR-0003** (transport profiles; alert delivery by profile; closes D-001) → 1.8.3. Touches host isolation: second approval required |
| Branch | `task/T-0022-alerting`, **on top of `task/T-0020-sc04-pg-connections`** (#38): the monitoring files build on T-0020's. Its PR opens after #38 merges |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | the read-only discovery, the deploys and the verification. vm-166 after the T-0020 AFTER-MERGE; vm-095 only after PR #36 (T-0021) merges |

## Goal (plain language)

Today Argus investigates only when someone asks (`argus diagnose`) or on a schedule. The alert rules exist, but no
alert ever reaches Argus. After this task:
- each VM has its own **Alertmanager**, **node-exporter** (host CPU, memory, disk, load) and **cAdvisor** (CPU,
  memory and throttling per container), all `argus-v18-*`;
- the Argus scheduler **pulls** the firing alerts from each host's Alertmanager through the existing path (vm-166:
  the restricted SSH tunnel) and opens an incident for each one, with the same identity as a webhook would have;
- an incident in the lab (for example SC-03, the cache stops) is **detected and investigated without anybody
  typing a command**.

## Decisions (2026-10-08, `conantkd`)

- **D-001, option B, as transport profiles** ([ACR-0003](../../architecture/changes/ACR-0003-transport-profiles.md)):
  `direct-private` | `wireguard-overlay` | `restricted-ssh`, chosen by configuration. This deployment is
  `restricted-ssh`: forward-only, so alerts are **pulled**. The push webhook stays for profiles with bidirectional
  connectivity.
- **Pull from Alertmanager** (`/api/v2/alerts`), not Prometheus `ALERTS`: grouping, silences, and the webhook's
  identity (`fingerprint + startsAt`), so a later push does not duplicate incidents.
- **Argus-owned exporters**: the node-exporter and cAdvisor already on vm-166 belong to the protected deployment
  (`infrastructure/environment.md` §4) and are never scraped.

## Design (to confirm step by step)

- **Use case `HandleAlertNotification`** (`argus/application/`): translates one `AlertNotification` into intake.
  - Target from labels: `argus_host` + `container` (or `owner`) → `container`; `argus_host` alone → the `host` target.
  - Identity `alert:<fingerprint>:<startsAt>` (§6.6). Only `firing` alerts open incidents.
  - A target outside the inventory is refused and audited.
  - The webhook (`adapters/inbound/http.py`) and the reconciliation both call it. Today the webhook does the
    translation itself.
- **`AlertSourcePort.firing_alerts(host)`**: adapter `alerts_alertmanager.py`.
  - `GET <alertmanager>/api/v2/alerts?active=true&silenced=false&inhibited=false`.
  - Every alert must carry `argus_host` equal to the host asked; one with another host is dropped and logged, never
    reassigned (no cross-host fallback).
  - The URL comes from the inventory: a new `alertmanager` entry per host. Like `prometheus`, it has no executor token.
- **`ReconcileFiringAlerts`** in the scheduler.
  - `reconcile_firing_alerts: {enabled, every_s}` in `schedules.yaml`, default 60 s.
  - Each pass: per host, the firing alerts go to `HandleAlertNotification`.
  - A host whose Alertmanager does not answer is logged and audited once per outage, and the other hosts go on.
  - Dependency rule 15 stays: the scheduler imports no detector, runner, graph or model.
- **Monitoring compose (both hosts)**:
  - `argus-v18-alertmanager` (route: group by `alertname, argus_host, container`; no receiver that leaves the host).
  - `argus-v18-node-exporter`.
  - `argus-v18-cadvisor` (read-only mounts; memory limit).
  - Prometheus: `alerting:` to the local Alertmanager, plus scrape jobs for both exporters with the `argus_host` label.
  - vm-166: Alertmanager on `127.0.0.1:<port>`, one `-L` more in `argus-v18-tunnel`, one `permitopen` more on the
    tunnel account.
  - Ports and image tags: from discovery (step 2).
- **Signals and rules** (they also feed SC-05/SC-06 later): host disk-used ratio, host CPU, memory available,
  container CPU throttling. The alert rules carry `argus_host` and `container`.

## Steps

1. **ACR-0003** and `ARCHITECTURE.md` 1.8.3 (text only); D-001 → decided. Review by `juanbetancurm` (second approval).
2. **Discovery (read-only, both VMs):**
   - free RAM and disk, CPU architecture, cgroup version;
   - the free ports in 18000–18799;
   - ARM64 image tags for Alertmanager, node-exporter and cAdvisor;
   - the subnets in use;
   - the tunnel account's current `permitopen` list.
3. **Code, tests first:** `HandleAlertNotification` (and the webhook through it), `AlertSourcePort` + adapter + fake,
   `ReconcileFiringAlerts` + scheduler flag, inventory `alertmanager`, compose/Prometheus/Alertmanager files, signals and
   rules, tunnel forward.
4. **Deploy vm-166:** monitoring services, the tunnel account's `permitopen`; NO INTERFERENCE.
5. **Deploy vm-095** (after #36): monitoring services, the tunnel forward, the agent (scheduler) rebuilt with
   reconciliation enabled; NO INTERFERENCE.
6. **Verify:**
   - SC-03 (the cache stops): `DependencyProbeFailed` firing → pulled → incident opened by `alertmanager@vm-166` →
     DIAGNOSED;
   - the next passes do not duplicate it;
   - a vm-095 alert works too;
   - reset, LAB BASELINE OK, NO INTERFERENCE.
7. Brain, PR.

## Out of scope

- Resolved alerts closing or annotating incidents (`AlertOccurrence`): the alert identity is ready for it; a later
  task.
- The push webhook on this deployment: needs a bidirectional profile.
- SC-05 / SC-06 scenarios: they use the signals added here, in their own tasks.

## Red seen / evidence

- **Step 1 (2026-10-08):** ACR-0003 proposed; `ARCHITECTURE.md` 1.8.3; D-001 decided (second approval pending).
- **Step 2 (2026-10-08, read-only, both VMs):** 1 vCPU aarch64, cgroup v2, ~4.8 GiB available on each; vm-166 has the
  three images already (`prom/alertmanager:v0.34.0`, `quay.io/prometheus/node-exporter:v1.12.1`,
  `ghcr.io/google/cadvisor:v0.60.5`); 18091 free; tunnel `permitopen` 18090, 18701-18704
  ([evidence](../../execution/history/T-0022/step-02/evidence.md)).
- **Step 3 (2026-10-08, code, tests first):** `tests/test_t0022_alerting.py`, 17 tests.
  - **red:** 16 failed for the right reason (no `AlertNotification`, no `argus.application.alerts`, no Alertmanager
    adapter, no `load_reconcile`, no `alertmanager` in the inventory, no services, no `alertmanager.yml`, no
    `alerting:`, no tunnel forward, no new signals); the rule-15 guard passed (it must stay green).
  - **green:** 17/17; full suite **186 passed, 7 skipped**. The webhook now goes through `HandleAlertNotification`
    (its old test used `startsAt: "t"`, not a time: now RFC 3339, as Alertmanager sends).
  - `promtool check config` both hosts and `check rules` (5 rules), `amtool check-config`, `docker compose config`
    with both overlays: valid.
  - Local smoke test (Docker Desktop, removed afterwards): cAdvisor healthy and publishing the CFS throttling
    counters; Alertmanager answers `/api/v2/alerts`; node-exporter needed `pid: host` to read the host mount table
    (without it: only its own mounts), and `rslave` was dropped (refused by Docker Desktop, not needed). The root
    filesystem `/` is an `overlay` on Docker Desktop (excluded by design): checked on vm-166 in step 4.
- **Step 4 (2026-10-08, vm-166, mutating):** deploy `dde432f`; `permitopen` 18091 added (backup kept); the three
  services Up, Prometheus recreated; every `argus-v18-*` job `up=1`; root filesystem present (disk 0.27 used);
  cAdvisor sees `argus-lab-api`; 1 Alertmanager, nothing firing; ~55 MiB for the three new services; LAB BASELINE
  OK; nonint: only the new listener `127.0.0.1:18091` ([evidence](../../execution/history/T-0022/step-04/evidence.md)).
