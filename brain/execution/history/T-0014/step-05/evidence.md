# T-0014 step 05 — evidence (2026-10-08, juanbetancurm, session 001732996b14)

Goal: prove the api / worker / scheduler split on vm-095: the three containers run from one image, a killed
worker's run is taken back and **resumed from its checkpoint**, and a schedule is submitted once per slot and
coalesced while its target is busy. Only vm-095 moved (to `task/T-0014-worker-scheduler`); vm-166 stayed on
`task/T-0020-sc04-pg-connections`, untouched. `code.bash` here holds the step 5c blocks (5a and 5b used the same
patterns: deploy, crash, read the audit trail).

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

## 5a — deploy and H-1 through the worker

| Check | Observed | Result |
|---|---|---|
| checkout + migration | `DEPLOY OK: e4be0f9`; `+ 003_worker_lease applied` | OK |
| containers | `argus-v18-agent` runs `argus api`, `argus-v18-worker` `argus worker`, `argus-v18-scheduler` `argus scheduler`; `api healthz: 200` | OK |
| scheduler | `1 schedules, 0 enabled` (shipped file: nothing scheduled) | OK |
| H-1 | `--check` of `vm-095/container:argus-lab-api` HEALTHY, run by the worker (`running inc_4e1ae094267e`) | OK |
| isolation | `LAB BASELINE OK`; `NO INTERFERENCE` | OK |

## Fix found before the crash test

Reading the worker loop before killing it showed that expired claims were recovered **only at start**. Docker
restarts a killed worker within seconds, while the dead worker's lease (300 s) is still live, so its run would have
stayed `running` forever. Commit `169ca07`: the worker re-checks every `recover_every_s` (30 s) while it runs; test
`test_a_running_worker_takes_back_a_claim_that_expires_later` (red seen). Deployed on vm-095 and the three
containers rebuilt before 5b.

## 5b — the worker killed in the middle of an investigation (SC-02)

- **Run 1 (inconclusive):** SC-02 `inc_d4b46c33f746` DIAGNOSED, but the investigation ended before the kill, so it
  proved only that Docker restarts the killed worker (`Up 14 seconds`). The block was rewritten to kill 2 s after
  the worker logs `running inc_…` and to say whether the run was still in progress.
- **Run 2 (OK):**

| Time (UTC) | Observed |
|---|---|
| 12:45:04 | worker `running inc_a9ddbfee2626 on vm-095/container:argus-lab-worker`; audit `incident.started`, `decision.strategy_selected` (`container_restart_loop`, `model_loop`), `recall.passages` (RB-008, RB-001) |
| ~12:45:06 | `run still in progress at the kill: yes`; host-side `kill -9` of the worker process (exit 137) |
| ~12:45:20 | `argus-v18-worker Up 14 seconds` (restarted by Docker; the dead worker's lease still live) |
| 12:50:09 | `WARNING argus.worker requeued 1 runs whose claim expired`; `running inc_a9ddbfee2626` (same incident); audit `incident.resumed {"next": ["investigate"]}` |
| 12:50:14-17 | `container.status`, `container.events`, `container.logs`, `container.resources`: all `ok` |
| 12:50:26 | `decision.conclude`, `incident.recorded`: **DIAGNOSED**, `container_restart_loop`, root cause `vm-095/container:argus-lab-worker` (missing `/etc/worker/config.yml`, exit 1, not OOM), confidence high, 4 cited observations |

The steps done before the kill (start, strategy, recall) were **not repeated**: the run continued from its
checkpoint. The take-back came ~5 min after the kill (lease 300 s + the 30 s re-check), with no second incident.
Lab reset (SC-02 removed): `LAB BASELINE OK`; `NO INTERFERENCE`.

## 5c — the scheduler

One schedule enabled **temporarily** in the VM checkout (`t14-step5c`, `*/5 * * * *`, health check of the healthy
lab twin `vm-095/container:argus-lab-api`; a healthy check calls no model), then the shipped file restored.

| Block | Observed | Result |
|---|---|---|
| C.1 enable | `1 schedules, 1 enabled`; `t14-step5c 2026-10-08T13:05:00+00:00: submitted inc_e9e1e74fc6d2`; worker `running inc_e9e1e74fc6d2`; `closed|no_incident` | OK |
| (13:10 slot) | `inc_95e6327a6287` `closed|no_incident` (ran before the worker was stopped) | OK |
| C.2 worker stopped (13:11:31) | `13:15:00: submitted inc_d73578e7a40e`; row `queued` (no worker) | OK |
| C.3 scheduler restarted (13:16) | `1 schedules, 1 enabled`, **no new submission** for the 13:15 slot; still one row per slot | OK |
| C.4 next slot | `13:20:00: vm-095/container:argus-lab-api is busy (inc_d73578e7a40e), coalesced`; audit `schedule.coalesced {"schedule_id": "t14-step5c", "scheduled_for": "2026-10-08T13:20:00+00:00"}` on that incident; no new row | OK |
| C.5 worker started (13:23) | `running inc_d73578e7a40e` (waited ~8 min < 900 s, so not stale); `closed|no_incident` | OK |
| C.6 undo | VM checkout clean (`git status --short` empty); `1 schedules, 0 enabled`; 3 `argus:` lines running; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |

nonint-check: NO INTERFERENCE on vm-095 after 5a, 5b and 5c. vm-166 not touched.

**Result:** step 5 done. vm-095 runs `task/T-0014-worker-scheduler` `169ca07` (three Argus programs, no schedule
enabled) and goes back to `main` after the merge (checkout only; the images stay). Rollback if needed:
`ARGUS_AGENT_CMD=serve` for `argus-v18-agent`, worker and scheduler stopped.
