# T-0029 — SC-08: nginx in front of a slow upstream (`nginx_upstream_failure`, RB-015)

| Field | Value |
|---|---|
| Status | `done` 2026-10-10 (step 2: SC-08 DIAGNOSED on vm-166, root cause the slow upstream, no side alert) |
| Phase | 11 — synthetic incidents ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) §7: SC-08 "nginx → slow upstream with 502s") |
| Architecture | no change (no ACR): §3 class table (`nginx_upstream_failure` · RB-015 · branches RB-002, RB-003 · `plan_then_reason`); the probe is a function of `argus-exporter`, which already runs the dependency probes |
| Branch | `task/T-0029-sc08-nginx`, from `main`; the VM proof runs on a branch that merges it with what the VMs run |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | step 2: the target services, Prometheus rules and the lab proxy/upstream on vm-166; the agent image on vm-095 |

## Goal (plain language)

A reverse proxy whose upstream is too slow answers `504 Gateway Timeout` (or `502` when the upstream fails): users
see errors although the proxy itself is healthy. SC-08 puts nginx (2 s read timeout) in front of an upstream that
answers after 5 s. Argus must detect the gateway errors, open a `nginx_upstream_failure` incident on the proxy and
name the upstream as the cause, not the proxy.

## Decisions (2026-10-10, `conantkd` + agent)

- **Measurement: a synthetic HTTP probe** (option a). The exporter GETs every declared `http_endpoints` of an active
  container every 10 s and publishes `argus_http_probe_status`, `_gateway_error` and `_duration_seconds`. General (any
  HTTP service), no new component, no traffic generator needed. Option b (nginx access-log metrics: real traffic,
  per route, who produced the 5xx) needs a new Host T component and a field allowlist for logs (an ACR): not now.
- **Gateway errors are 502 and 504 only**: the proxy's own answers when its upstream fails or is too slow. An app's
  503 is not one (the SC-03 api answers 503 when its cache is down: that is `dependency_unavailable`).
- Signal `http_gateway_error_ratio_5m` (the worst endpoint's 5-minute share); the class matches at **0.5**; alert
  `HttpGatewayErrors` (`for: 2m`, labelled `owner`, which the intake maps to the target).
- Only `nginx_upstream_failure` now; the generic `http_errors_latency` (RB-011) later.
- Lab (profile `sc08`): `argus-lab-nginx` (`nginx:1.27-alpine`, `proxy_read_timeout 2s`) → `argus-lab-slow` (answers
  after `DELAY_S=5`), both on `argus-lab-app`, small limits, `restart: "no"`.
- Baseline: the proxy's one upstream in scope is the root cause (down: H1; running: too slow, H3); more than one
  candidate → escalate.

## Steps

1. **Code and tests** (done 2026-10-10): `tests/test_t0029_sc08_nginx.py` (12, red seen 12/12: nothing existed); 6
   evaluation cases `tests/eval/cases/nginx-*.yaml` (5 class + 1 under the threshold; baseline 6/6, hard 0 0 0); the
   rendered `vm-166.json` (`http_probes`).
2. **VMs:** a proof branch (what the VMs run + this branch); vm-166: target services (the exporter's probe),
   Prometheus rules, `--profile sc08 up`; vm-095: agent image, Prometheus rules. Expected: `HttpGatewayErrors` after
   ~4 minutes, a `nginx_upstream_failure` incident on `vm-166/container:argus-lab-nginx`, DIAGNOSED naming
   `argus-lab-slow`; no alert on the SC-03 api; down: the alert resolves. NO INTERFERENCE. **Done 2026-10-10**
   ([evidence](../../execution/history/T-0029/step-02/evidence.md)): `inc_46cdffa78fdb` DIAGNOSED (high), root
   cause `argus-lab-slow`; the api's probe gave 200, no other alert; resolved 02:25:01. Both VMs stay on
   `task/T-0029-vm-proof` `eebfa72` until the stack, T-0028 and this task merge.

## Done when

SC-08 on vm-166 is DIAGNOSED from the pulled alert with the slow upstream as the root cause, no other alert fires
because of the probe, and both VMs show NO INTERFERENCE.
