# AFTER-MERGE (main) step 01 — evidence (2026-10-12, run by conantkd, session 4f8a9d4f8dc1)

Goal: both VMs from `task/T-0019-batch3b-host-verbs` (`9ac49ec`) to `main` (`d34f0cb`) after PRs #97–#111. Held until
#109 (`/tcp` 8 s budget) and #110 (redactor keeps only declared paths) were merged, as `juanbetancurm` asked in #110.
The agent ran the blocks of [`code.bash`](code.bash) over ssh, in order, inside the lease (both VMs, until 05:32 UTC).

| Block | Expected | Observed | Result |
|---|---|---|---|
| M.1 markers | the same marker on both VMs | both `holder=conantkd session=4f8a9d4f8dc1` | OK |
| A.1 vm-166 → main | SESSION OK; DEPLOY OK (main); target services up; LAB BASELINE OK; NO INTERFERENCE | `SESSION OK`; baseline saved (63 lines); `DEPLOY OK: d34f0cbc4826 (main)`; `target services up: 5`; `commit=d34f0cb…`, `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged` | OK |
| A.1 vm-095 → main + agent | as above + BACKUP OK; one image, restarts 0, health 200, 20/20, 55/55, WRITE GATE CLOSED | `SESSION OK`; baseline saved (54 lines); `BACKUP OK` (1871433 bytes); `DEPLOY OK: d34f0cbc4826 (main)`; `target services up: 4`; agent, worker, scheduler recreated together, all on image `c3e928c989d3`, `running restarts=0`; `health 200`; `worker: no startup errors`; `20/20 database checks passed`; `55/55 checks passed`; `WRITE GATE CLOSED`; `commit=d34f0cb…`, `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| A.2 vm-166, 3c routes | api→cache 200 shared `argus-lab-app`; →nope 404; tcp attempts=3 ok, 3 succeeded; no address | `200 … shared ['argus-lab-app']`; `404 … not in this host's allowlist`; `200 … ok True, succeeded 3`; names only | OK |
| A.3 vm-095, agent's code path | check_connectivity ok; check_tcp_connection ok 3/3; snapshot in catalogue; redactor keeps the declared path and masks the URL secret; NO INTERFERENCE | `check_connectivity ok | … shared networks: argus-lab-app`; `check_tcp_connection ok | … 3/3 connected (ok 0.4 ms, ok 0.5 ms, ok 0.5 ms)`; `snapshot in catalogue: True`; `redactor: /opt/argus-v18/app/deploy/lab/nginx/default.conf GET /[REDACTED HIGH-ENTROPY]`; `NO INTERFERENCE` | OK |

State after this step: **both VMs on `main` `d34f0cb`** (vm-095's agent, worker and scheduler on one image built from
it). No model call.
