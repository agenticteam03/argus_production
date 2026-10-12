# T-0033 step 02 — evidence (2026-10-12, juanbetancurm, both leases, session 351b0fdf7301)

Deploy of `main` `244453b` (#91–#95: OP-012, T-0033, EVAL-3) and one rotation of vm-166's `host_probe` token.
Tokens were never printed; only 12-character hashes of the new token.

## Deploy

| Check | vm-166 (D.1, checkout only) | vm-095 (D.2, agent/worker/scheduler) |
|---|---|---|
| session | SESSION OK | SESSION OK |
| deploy | `DEPLOY OK: 244453bca0e6 (main)` | backup OK (`argus-20261012T175222Z.dump`); `DEPLOY OK: 244453bca0e6 (main)` |
| services | none rebuilt (no target code changed); `rotate-token.sh` present | 3 recreated, one image `8d5bb11aa480`, running, restarts 0; worker started `17:53:13.64Z`; health 200 |
| checks | token `600 root:root` | 20/20 database checks; `phase3_check` 55/55; `token reload: True \| incident counters: True`; WRITE GATE CLOSED |
| state | `commit=244453b…`, `ref=main`, LAB BASELINE OK, NO INTERFERENCE | `commit=244453b…`, `ref=main`, LAB BASELINE OK, NO INTERFERENCE |

## Rotation (`report` on `vm-166/host:vm-166`: the evidence pack, no model call)

| Step | Result |
|---|---|
| T.1 report #1, before | `inc_0c261186a482`: `get_host_memory` ✓, `get_host_cpu` ✓; UNSUPPORTED → escalated |
| T.2 `rotate-token.sh host_probe` on vm-166 | `TOKEN ROTATE … argus-v18-host-probe recreated; sha256 e978168e4e0a`; token `600 root:root` (unchanged), `.prev` `400 root:root` |
| T.3 report #2, agent holds the old token | `inc_80d405b583de`: both reads `✗ error (forbidden): HTTP 401 unauthorized`; UNSUPPORTED → escalated (no crash); worker restarts 0, started `17:53:13.64Z` |
| T.4 the agent's copy (laptop ssh pipe) | hashes equal: vm-166 `e978168e4e0a`, vm-095 `.new` `e978168e4e0a` |
| T.5 copy in place, report #3 | token and `.prev` `400 10011:10011` (as before); `inc_fda8fb3307eb`: both reads ✓ again; UNSUPPORTED → escalated; **worker restarts 0, started `17:53:13.64Z` (not restarted)**; vm-095 NO INTERFERENCE |

The tools process picked up the new token on its next rejected read, without a restart. The rotation window (T.2 to
T.5) gave `forbidden` reads and escalations, never a crash or a read attributed to the wrong target.

## Deviations

- T.4's first hash lines used `sudo tr … < file`: the redirection ran without sudo (`Permission denied`, the hash of
  empty input). Corrected while running (`sudo cat file | tr …`); the archived `code.bash` has the corrected lines.
- vm-166's NO INTERFERENCE after the rotation (the optional last line of T.5) was not pasted; vm-166's D.1 check and
  vm-095's final check report NO INTERFERENCE.

Leases released (R.1).
