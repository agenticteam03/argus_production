# T-0029 step 02 — evidence: SC-08 on vm-166, nginx in front of a slow upstream (2026-10-10, conantkd, session d550d6afba41)

Mutating (vm-095: agent processes, Prometheus rules; vm-166: target services, Prometheus rules, the SC-08 lab pair),
run by the agent over SSH on the proof branch `task/T-0029-vm-proof` (= `task/T-0028-vm-proof`, which the VMs ran,
+ this task). `code.bash` in this folder. Sanitized: no addresses, no secrets.

| Check | Result |
|---|---|
| Deploy | both VMs `DEPLOY OK: eebfa722b1fc (task/T-0029-vm-proof)`; vm-095 agent, worker, scheduler recreated, Prometheus recreated; vm-166 target services rebuilt (the exporter's HTTP probe, `http_probes` in vm-166.json), Prometheus recreated |
| SC-08 up | `argus-lab-slow` and `argus-lab-nginx` started 02:13:30 (`nginx:1.27-alpine` pulled) |
| The probe | `argus_http_probe_status`: **`argus-lab-api` 200**, **`argus-lab-nginx` 504** (nginx's 2 s read timeout, the upstream answers after 5 s) |
| Alert | `HttpGatewayErrors` for `owner=argus-lab-nginx`, firing **02:16:01** (2 minutes after the first 504s) |
| Incident | pass 02:17:01 `{'started': 1}` → **`inc_46cdffa78fdb`** on `vm-166/container:argus-lab-nginx`: **`nginx_upstream_failure`, DIAGNOSED, confidence high, root cause `vm-166/container:argus-lab-slow`**. Findings: "100% of the probes through its endpoint got a gateway error (502/504)". The model: the upstream's logs show `GET /` answered after 5 s and broken pipes after the proxy gave up, matching nginx's "upstream timed out while reading response header"; nginx is the victim; "do not restart or increase timeouts speculatively". Reads: container status, health, logs, resources |
| No side alert | no alert from the api's probe (200; an app's 503 is not a gateway error by design); the scheduler opened only this incident |
| SC-08 down | `--profile sc08 down` at 02:19:06 removed only `argus-lab-nginx` and `argus-lab-slow`; `argus-lab-api`, `-cache`, `-db` up, LAB BASELINE OK |
| Resolved | no active alert on vm-166 at 02:24:07 (the 5-minute average drained); the occurrence of `inc_46cdffa78fdb` resolved at 02:25:01 (T-0026) |
| Baseline | both VMs on `task/T-0029-vm-proof` `eebfa72`, LAB BASELINE OK, no SC-08 container left, **NO INTERFERENCE** |

**Result:** SC-08 DIAGNOSED from the pulled alert, the slow upstream named as the root cause and the proxy as the
victim; the probe raised no alert elsewhere. Both VMs stay on the proof branch until the stack, T-0028 and this task
merge.
