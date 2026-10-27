# DEPLOY-7f137da step 01 — evidence: X-2, phase 19 and the reference corpus on vm-095 (2026-10-27 UTC, conantkd)

Goal: put main `7f137da` on vm-095: phase 19's private login and approvals (#324, #347; migration 017, the edge's
`X-Argus-Ops`) and the reference corpus (#349, #351, #352: `argus-v18-weaviate`, the corpus folders, the bundle
installed and indexed). vm-166 gets the checkout only (no target, lab or monitoring change since `bdcd048`). Run by
conantkd's agent over ssh at conantkd's explicit request, both leases (session `a0224ada`, claimed 16:56Z, released
after D.7). Commands: [`code.bash`](code.bash). Sanitized: no address, token or key.

| Block | Observed | Result |
|---|---|---|
| D.1 vm-166 | marker; `before` saved (63 lines); `ref=bdcd048`, `LAB BASELINE OK` | OK |
| D.2 vm-095 | `ref=798b69a`, `LAB BASELINE OK`; `before` saved (54 lines); evaluations running: 0; `BACKUP OK` (2549617 bytes, 16:57Z); **`VERIFY OK: 31 tables, 33935 rows match`**; `DEPLOY OK: 7f137daa836f (7f137da)`, deploy event recorded; **`+ 017_ops_session applied`**, runtime password set | OK |
| D.3 vm-095 | folders: see note 1; `argus-v18-weaviate-data` created; weaviate `Created`, `Started`; agent, worker, scheduler `Recreated`, `Started`; `health 200`; **`94/94 database checks passed`**; all four `running restarts=0` | OK |
| D.4 vm-095 | **`verified and installed in /corpus: 20251 passage(s) from 8 source(s)`** (bundle built 06:13Z); keyword search from the worker returns podman and docker-docs passages; **`indexed 20251 passage(s)`** in Weaviate; the worker reads `/corpus` and cannot write it | OK |
| D.5 vm-095 | UI `Recreated`, `Started`, `running restarts=0`; `X-Argus-Ops` in `proxy.conf` and `locations.conf`; `nginx -t` successful | OK |
| D.6 vm-166 | `DEPLOY OK: 7f137daa836f (7f137da)` | OK |
| D.7 both | **`WRITE GATE CLOSED`** on both (vm-095: agent, worker, scheduler `gate_open=0 write_capabilities=0 action_gateway_resolves=0`); API 200, public UI 200; agent, worker, scheduler, weaviate, UI, postgres, tunnel `running restarts=0`; worker error lines: 1, a metric name (`argus_http_probe_gateway_error`) in a successful query; `LAB BASELINE OK`; **`NO INTERFERENCE`** on both | OK |

## Notes

1. **The corpus folders were created by Docker, not by the block.** `install -d -o 10010` refused the uid (no such
   user on the host), so the bind sources did not exist at `up` and Docker created them owned by root. Found before
   any import; fixed with `chown 10010:10010` and `chmod 0750`; the agent wrote both folders, the worker only read
   `/corpus`. The archived block uses `mkdir` then `chown`.
2. **Hybrid retrieval stays off.** After the index Weaviate holds 425 MiB of its 512 MiB limit, above its
   `GOMEMLIMIT` of 400 MiB (the 2026-10-15 trial measured 210 MiB with 6,510 objects; this bundle has 20,251).
   `ARGUS_CORPUS_RETRIEVAL` stays `keyword` (the default) until the limit is reviewed; the index is built.
3. **`ops/deploy.sh` names no rebuild for `deploy/ui/`**: the edge's `X-Argus-Ops` (#347) needed D.5, found by reading
   the diff. A hint line for `deploy/ui/` would have caught it.
4. Not in this window, on purpose: phase 20's tunnel forward, the worker's network and the target's `container_id`
   (#354–#356, not merged): a second, short window after they merge. An `admin` user for the corpus screen (T-0057)
   is not created here.
5. The bundle stays at `/tmp/argus-corpus-base.tgz` and extracted under `/opt/argus-v18/corpus-staging/base`.
