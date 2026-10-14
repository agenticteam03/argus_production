# DEPLOY-151 step 01 — evidence: vm-095 to `main` 37822c9 (#151, #153) (2026-10-14, juanbetancurm, session f10105709128)

Goal: vm-095 on `main` after #151 (ACR-0012: the UI may start an investigation; ACR-0014: host metrics) and #153
(record only). Before: vm-095 on `main` `ccc810e` (AFTER-MERGE of the morning). vm-166 not touched: no target-service
change in #151/#153. Lease: vm-095 only. Commands: [`code.bash`](code.bash), adapted from
`AFTER-MERGE-main-2026-10-14/step-01`. The public address is not written here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| D.1 laptop | vm-095 lease claimed (`DEPLOY-151`); the VM's marker `holder=juanbetancurm session=f10105709128` | OK |
| D.2 vm-095 → `main` + agent | `SESSION OK`; baseline saved (54 lines); `BACKUP OK` (2151778 bytes); `DEPLOY OK: 37822c9dab53 (main)`; migrations 001–006 already applied; agent, worker, scheduler recreated together on image `21638738f2af`, `running restarts=0`; `health 200`; `worker: no startup errors`; `20/20`; `55/55`; `WRITE GATE CLOSED` | OK |
| D.3 vm-095 UI (public mode) | `argus-v18-ui` recreated: `running health=healthy restarts=0`, ports `0.0.0.0:443`, `0.0.0.0:80` only; through the edge: `GET /api/v1/targets` 401, `/api/v1/host-metrics` 401, `/api/v1/me` 401 (the new routes exist and need a login), `GET /docs` 404, `POST /api/v1/investigations` 401; `commit=37822c9…` `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| D.4 laptop | lease released on vm-095 | OK |

## In the UI after the deployment (operator, browser)

- After a full reload and a new login (the new build asks for `scope=investigate`; a session from before the
  deployment holds a read token, so the investigation form stays hidden), the form "Start an investigation" appears.
- Host metrics: both hosts `Live` with CPU, memory and root-disk percentages and a sample time; the chat answers
  "Check Host T memory usage" with the measured value and its sample time.
- A `report` started from the form on `vm-166/container:argus-lab-backend` (`inc_fb9c5ab5add0`, principal
  `juanbetancurm`, trigger `manual`): the container did not exist at the time (SC-07 reset), so `detect` found no
  fresh samples and the run ended `undiagnosable`, escalated, with an evidence pack of 6 reads (all `error`), no class
  and no claimed cause, in 4 s. The expected safe answer for an absent target.

## The alert path, same day (before this deployment)

SC-07 on vm-166 started at 15:36:40 UTC with no request: the scheduler pulled `DependencyProbeFailed` and opened
`inc_edfb8086446a` (`vm-166/container:argus-lab-client`); at 15:39:19 it was `diagnosed`, `dependency_unavailable`,
root cause `vm-166/container:argus-lab-backend` ("shares no network … restarting either will not help"),
`decided_by: rule` (D-003's baseline, no model call). Reset afterwards (0 lab containers left).

## Not done here

- The quota test from the UI (the third queued investigation answered 429) was not run.
- The operator note under the chat still says "Read-only in this release" (`frontend/src/routes.js`, `ROLE_INFO`);
  outdated since ACR-0012.
- The VM's `SESSION` marker still names `juanbetancurm` after the release; the next holder writes their own.
