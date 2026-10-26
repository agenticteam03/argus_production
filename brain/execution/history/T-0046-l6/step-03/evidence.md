# T-0046 L6 step 03 — evidence: SC-03 and SC-07 live on main 16028c7 (2026-10-26 UTC, conantkd)

Goal: T-0046's step after #322's deploy (DEPLOY-16028c7): run SC-03 and SC-07 once each and check that the probe
history is replayed at its source times and that the incidents read `network.link_states`. Both classes run the
deterministic baseline (no model call). Both leases (session `13d7ed00`). S.1 ran in conantkd's terminal (the runner
asks the Argus password); the reads after it ran by conantkd's agent over ssh, read-only. Commands:
[`code.bash`](code.bash). Sanitized: no name, address, password or key.

| Run | Observed | Result |
|---|---|---|
| S.1 SC-03 | **PASS** (`inc_1b392a41406e`, 19 s): `dependency_unavailable`, baseline, `diagnosed`, root cause `vm-166/container:argus-lab-cache`; reads `container.status` and **`network.link_states`** | PASS |
| S.1 SC-07 | **PASS** (`inc_0da70b2987db`, 19 s): `dependency_unavailable`, baseline, `diagnosed`, root cause `vm-166/container:argus-lab-backend`; reads `container.status` and **`network.link_states`**; the diagnosis cites the recorded broken link `argus-lab-client -> argus-lab-backend` | PASS |
| Link rows (read-only) | `api -> cache` **`broken` at 05:06:02, `ok` at 05:06:17**: a 15 s transition between two 60 s scheduler ticks, kept at its source times (L5 would have lost it); `client -> backend` **`broken` at 05:06:32** (L5 on 2026-10-21 recorded no row for SC-07), then **`unknown` at 05:08:17**, 90 s after its last sample (05:06:47), its state outside SC-07 | as expected |
| Lab | `LAB BASELINE OK` on vm-166 after the runs | OK |

## Notes

1. `client -> backend` has no probe sample outside SC-07, so it returns to `unknown` (as in L5's baseline), here at the
   staleness limit after the last sample: the rule #322's review asked for, seen live.
2. The runner's password prompt echoed the second entry in conantkd's terminal; that line was removed from the local
   `output.bash` (gitignored, never committed) and is not reproduced here.
