# T-0037 step 2 — evidence (2026-10-13 UTC, conantkd's agent over ssh; both leases, session 4f8a9d4f8dc1)

Goal: the four new read-gateway routes against vm-166's real Docker, without changing a service.

How: the branch's `services/target/service.py` (fetched into the checkout's git, `git show` to `/tmp`; the checkout
itself unchanged) ran in a one-off `python:3.12-alpine` container with the Docker socket **read-only** and vm-166's
rendered target config read-only; `read_gateway(...)` was called directly. `/tmp` removed after.

| Route | Observed (run 2, `5b09ec0`) | Result |
|---|---|---|
| `/containers/argus-lab-api/top` | 2 processes, `command: python`; no arguments | OK |
| `/containers/argus-lab-db/top` | postgres processes, `command: postgres` (run 1 showed `postgres:`, see below) | OK |
| `/docker/df` | images 14 (1930180033 bytes, 5 unused = 535081469), containers 13 (0 stopped, writable 13438976), volumes 9 (2381466920 bytes, 7 unused = 2342121334), build cache 726097947 bytes; no name | OK |
| `/containers/argus-lab-api/logs_window?minutes=30&stream=stderr` | `lines: []` | OK (see below) |
| `/containers/argus-lab-db/logs_window?minutes=120` | `lines: []` | OK (see below) |
| `/containers/argus-lab-{api,db}/search?pattern=error&minutes=120`, `restart` | `matched: 0` | OK |
| `/containers/argus-lab-api/search?pattern=passw.*` | `Err 400 pattern must be one of [...]` | OK (refused) |
| `/containers/argus-v18-read-gateway/top` | `Err 404 not in this host's allowlist` | OK (refused) |
| after | `checkout local modifications: 0`; `NO INTERFERENCE` | OK |

- **Empty log windows are correct:** the lab containers last wrote a log line on 2026-10-10 (`docker logs --tail 1`:
  `argus-lab-api` 02:39 UTC, `argus-lab-db` 14:01 UTC, `argus-lab-cache` 02:39 UTC; `--since 2h`: 0 lines each). The
  parsing of real lines (multiplexed frames, stdout / stderr) is covered by the tests.
- **Fix found here:** run 1 (`bf3c41b`) named PostgreSQL's processes `postgres:` (its process titles are
  `postgres: checkpointer`, …); `5b09ec0` strips the trailing colon (test extended).
- The volumes' unused share (7 of 9, 2.3 GB) is what `get_docker_disk_usage` is meant to show in a disk incident.
