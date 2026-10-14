# AFTER-MERGE (main) 2026-10-14 step 01 — evidence (conantkd's agent, session dc432c3ff537)

Goal: both VMs to `main` after #141 (the gateway's `error` pattern), #144 (T-0016 + ACR-0011 4a–4c), #145 (D-003),
#146 (4e record) and #147 (ACR records). Before: vm-166 on `main` `ad72617`; vm-095 on `task/T-0016-playwright`
`8ee48c4` (the public UI edge). Both leases. Commands: [`code.bash`](code.bash). The public address is not written
here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| A.1 vm-166 → `main` `ccc810e` | `SESSION OK`; `DEPLOY OK: ccc810eb622c (main)`; `target services up: 5` (the read gateway rebuilt with #141's pattern); `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| A.1 vm-095 → `main` `ccc810e` + agent | `BACKUP OK` (2142642 bytes); `DEPLOY OK: ccc810eb622c (main)`; `target services up: 4`; migrations 001–006 already applied; agent, worker, scheduler recreated together on image `d72e20e45e2c`, `running restarts=0`; `health 200`; `20/20`; `55/55`; `WRITE GATE CLOSED`; strategies `dependency_unavailable: baseline`, `nginx_upstream_failure: baseline`, `health_check_failed: model_loop` (D-003); `argus-v18-ui` healthy on 0.0.0.0:443/80; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |
| #141 on vm-166 | the read gateway's pattern `(error|exception)s?\b|\b(traceback|fatal|panic)\b`; `search_logs` from vm-095's worker on `vm-166/container:argus-lab-api`: `ok | 0 lines matched 'error' in 60 min` | OK |
| the public UI after A.1 | `https://<PUBLIC_ADDR>/` 200 with a trusted chain; **`/api/v1/me` 502**; `/docs` 404 | **found** |

## Found: the edge answered 502 after the agent was recreated

- **The cause.** Nginx had resolved `argus-v18-agent` once, when it started. A.1 recreated the agent, worker and
  scheduler, the agent came back with another address on `argus-v18-core`, and every proxied API request failed.
  The app itself was still served.
- **Restored at once:** `docker exec argus-v18-ui nginx -s reload` gave `/api/v1/me` 401 and `/runbooks/index.json`
  401 again (the expected answers without a token). The outage lasted about 2 minutes, between the agent recreate
  (≈04:52 UTC) and the reload (04:54 UTC).
- **The fix** (`deploy/ui/nginx/http.conf`):
  - `resolver 127.0.0.11 valid=10s` (Docker's DNS);
  - the upstream `server argus-v18-agent:8000 resolve` with a `zone` (Nginx ≥ 1.27.3);
  - the upstream zone named `argus_api_upstream`: the first try reused `argus_api`, the `limit_req` zone, and
    `nginx -t` refused it.
- **Test:** `tests/test_acr0011_ui_edge.py::test_the_edge_follows_a_recreated_agent_without_a_reload` (real Nginx, a
  fake API recreated under the same name with a new address, no reload). **Red** without the fix, **green** with it;
  the file passes 25/25.
- **U.1 on vm-095:** `task/AFTER-MERGE-main-2026-10-14` `46ba3a3` deployed, `argus-v18-ui` rebuilt, healthy, its
  config with `resolve`. Then the agent was recreated **without reloading the edge**, and the public `/api/v1/me`
  answered 401 at once.
  - **This time Docker gave the agent its old address back** (`172.30.0.9` before and after), so the live run does
    not exercise the new resolution. The test above does.
  - `NO INTERFERENCE`.

## State after this step

- vm-166 on `main` `ccc810e`.
- vm-095 on `46ba3a3`, this record's branch: `main` + the resolver fix. It goes back to `main` as a checkout-only
  deploy once this PR is merged; the trees are equal then.
- The public UI is up: HTTPS with a trusted chain, the API answering through the edge, D-003 and #141 live.
