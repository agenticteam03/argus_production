# T-0020 step 03 — evidence: SC-04 on vm-166 (2026-10-07, conantkd, session 3307114120d3)

S.1 and S.3 were run by the agent over SSH; S.2 (`argus diagnose`, needs the password) by `conantkd`; the agent read
the saved report. Sanitized: no addresses, no secrets.

## Run 1 (~17:04 UTC) — not valid

- S.1: the leaker stopped at about 10 sessions: `can't fork: Resource temporarily unavailable` (lab `pids_limit: 32`).
- S.2 ran before the gate: `inc_b8370349ce57`, signals `db_up=1.0`, `db_connection_usage=0.0`, "no class matched",
  **UNSUPPORTED** with an evidence pack, no diagnosis claimed (correct for what it saw).
- Reset by `conantkd`: leaker gone, used 0, LAB BASELINE OK, NO INTERFERENCE.
- Fix (test first): the leaker has its own limits (`pids_limit: 64`, `mem_limit: 192m`), `b1e7176`.

## Run 2 (17:17–17:25 UTC) — valid

| Block | Expected | Observed | Result |
|---|---|---|---|
| S.1 start + gate | 16 sessions; usage >= 0.9 for 5 min; alert firing | `leaker: opened 16 sessions … each idle in transaction`; `used=16` from 17:18:09; `usage_5m=0.941` at 17:22:42; `alert_firing=1` at 17:23:12; `VERDICT S.1 OK` | OK |
| S.2 diagnose | class, RB-004, `inspect_database_health`, root cause the leaker, no DB restart | `inc_075fb0006098`: DETECT `postgresql_connection_exhaustion` (`db_connection_usage=0.941`, findings "94% of the usable connection slots in use for at least 5 minutes"); RECALL RB-004 **v1.0.1** (3 sections); step 1 the model read `inspect_database_health` (`16/17 client connections`) and `get_container_status` of the leaker; step 2 conclude. **DIAGNOSED**, root cause `vm-166/container:argus-lab-leaker`, confidence high: *"…caused by argus-lab-leaker retaining 16 client sessions in idle-in-transaction state, with transactions open for up to 401.7 seconds and waiting on ClientRead. These sessions consume 16 of 17 ordinary usable slots (94.1%) … The database itself is running and has no lock waits or blocked sessions; argus-lab-leaker is the root-cause producer, while other clients and the database service are victims. Human actions: urgently stop or otherwise contain the non-critical leaker under approved change control, have the DBA safely terminate the retained sessions if separately authorized, then verify ordinary admission and … fix the leaker's transaction/connection lifecycle … Do not treat freeing slots alone as a permanent fix."*; 4 cited evidence records | OK |
| S.3 reset | leaker gone; used 0; LAB BASELINE OK; NO INTERFERENCE | leaker gone; `used after reset = 0`; `LAB BASELINE OK`; **`DIFFERENCES ABOVE`**: one new anonymous volume | **STOP** (see below) |

## nonint-check difference (explained, cleanup pending)

`postgres:16-alpine` declares `VOLUME /var/lib/postgresql/data`. The leaker uses that image only for `psql`, so each
start created an anonymous volume, and `docker rm -f` left it. Two such volumes exist on vm-166, created exactly at
the two leaker starts (17:04:18 and 17:17:29 UTC), dangling, label `com.docker.volume.anonymous`. They are Argus's
(created by `argus-lab-leaker`), not another team's: the other anonymous volumes date from 2026-09-16/23 and were
not touched. nonint-check lists them as non-Argus because anonymous volumes carry no name.

- Fix (test first): the leaker mounts a tmpfs on `/var/lib/postgresql/data` (red: `KeyError: 'tmpfs'`).
- Cleanup: remove exactly those two volumes by ID (pending `conantkd`'s go; see the handoff).

**Result:** SC-04 diagnosed on the first valid run: detection from the metric, RB-004, the database read, the leaker
named, no restart of the database proposed. RB-004 `last_tested: 2026-10-07` (version 1.0.2). One run is not a
quality claim.
