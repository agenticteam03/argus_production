# RB-015 — NGINX/reverse-proxy upstream failure

## Metadata

```yaml
id: RB-015
title: NGINX/reverse-proxy upstream failure
status: draft
owner: Argus Team
version: 1.0.2
created: 2026-09-29
last_reviewed: 2026-10-09
source_review_date: 2026-09-29
last_tested: null
detector: nginx_upstream_failure
```

## Scope

Declared NGINX HTTP proxy routes and backend services. Record NGINX version/build/modules, route/upstream config fingerprint and Docker network. Features vary across versions and editions; no commercial health API is assumed. [Shared contracts](../RUNBOOK-CONVENTIONS.md) apply; use RB-002/003 as supported parent context, not an invented detector.

## Incident definition

Requests through the proxy fail or time out on the upstream path. A 502/503/504 alone does not identify whether NGINX generated it, an upstream returned it, or a different edge layer did; correlate upstream status, selected peer and error context. [NGINX upstream variables](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#variables)

## User / service impact

Identify affected virtual host/route and successful versus failed requests. A direct backend success may bypass headers, TLS, authentication or path rewriting used by the failing route.

## Trigger / detection conditions

Proposed rule: route's upstream error/timeout rate exceeds its accepted budget for 5 minutes with sufficient traffic; immediate investigation for confirmed broad outage. Binary failure can surface through RB-002. Unknown denominators and missing proxy logs do not establish error-free service.

## Symptoms

502/503/504, upstream connect/read timeout, no available peer, connection refused, header/protocol errors or one virtual host failing after a configuration change.

## Plausible causes / hypotheses

H1 backend down; H2 DNS/wrong address/port/network; H3 backend saturation/slow dependency; H4 TLS/SNI mismatch; H5 route/header/rewrite/config regression; H6 proxy capacity/resource failure; H7 upstream deliberately returns error; H8 stale cache masks partial failure.

## Required evidence

Paired edge/backend results for the same safe route contract, bounded proxy error/access metadata, selected peer/status/connect/response time, config fingerprint, backend state/dependencies/resources and change time. No request bodies or authentication headers.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `check_http_endpoint(url, timeout_s=3)` | Approved proxy/backend probe, subject to equivalent-route limits | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=150)` | Proxy and backend sanitized failures | `READ_ONLY_SENSITIVE` |
| `inspect_service_config(container, config='main')` | Only configured allowlisted proxy config | `READ_ONLY_SENSITIVE` |
| `check_dns(name)` | Backend name resolution and addresses | `READ_ONLY_SENSITIVE` |
| `check_tcp_connection(host, port, attempts=2)` | Bounded backend transport result and latency | `READ_ONLY_SAFE` |
| `get_container_status(container)` / `get_container_network(container)` | Backend/proxy identity and attachment | `READ_ONLY_SENSITIVE` |
| `trace_request_path(container)` | Declared dependencies to discriminate victims | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_proxy_upstream_history(service_id, route_id, minutes)` returns redacted peer/status/timing/counts, `READ_ONLY_SENSITIVE`; `validate_proxy_config(service_id, config_digest)` performs fixed syntax validation without exposing secrets, `READ_ONLY_SENSITIVE`; shared `check_tls_endpoint` and deployment history. A generic service reload is not currently available; validation does not itself authorize reload.

## Diagnostic workflow

| Step | Action / why | Interpret / next step |
|---|---|---|
| 1 | Fresh route probe and proxy error window | Bind actual source of error; wrong route/vantage → correct evidence before action. |
| 2 | Inspect selected upstream and declared config | Wrong peer/port/rewrite supports H2/H5; redact header/credential values. |
| 3 | Backend DNS/TCP/TLS and state | Failure routes to RB-009/016/008; proxy may be a victim. |
| 4 | Equivalent direct backend and dependency checks | Backend slow/error → RB-003/011; direct success weakens backend-wide outage but not route/header-specific faults. |
| 5 | Proxy resources/config change and upstream timing | Proxy saturation → RB-006/012; changed config → validate and owner review. No guessed timeout increase. |
| 6 | Preserve evidence, owner repair exact layer and verify end-to-end | Missing route equivalence/timing → multiple hypotheses, no speculative restart. |

## Decision tree

```text
proxy request fails -> error source/selected peer known?
  no -> collect bounded proxy metadata
  yes -> backend DNS/TCP/TLS fails? -> network/TLS/backend owner
         backend protocol slow/fails? -> dependency/performance owner
         equivalent backend succeeds? -> proxy config/capacity investigation
         missing equivalent probe? -> insufficient_evidence
```

## Evidence interpretation

`proxy_read_timeout` is a timeout between successive reads, not a universal total-response deadline. Retrying upstreams can also change behavior and risk duplicate work; inspect configured retry conditions. [NGINX proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_read_timeout) Diagnose the relevant phase before recommending a setting change.

## False positives and edge cases

Cached responses, retries across peers, wrong Host header, path rewriting, different backend credentials, stream/WebSocket timing, deployment drain, stale DNS resolution and truncated logs lacking the first error.

## Diagnosis outcome

All common outcomes allowed. Probable cause names peer/phase/config and evidence against backend-wide failure; generic 5xx alone remains insufficient attribution.

## Mitigation

Owner restores a tested config/peer or reduces harmful load. Restarting NGINX does not fix a failed backend. A controlled config reload is an operator action, not a model shell command.

## Recovery

Affected external routes meet status/latency expectations through NGINX and intended upstreams; backend capacity and proxy resources remain healthy.

## Root-cause correction

Repair peer/discovery/TLS/rewrite configuration, backend cause or capacity. Review retry/timeout budgets against application semantics rather than merely hiding errors.

## Action safety

Reload/rollback/restart/routing changes are `MUTATING_HIGH_RISK`. Require exact service/config digest, successful syntax validation, known-good prior version, protected auth/security directives, safe drain and correct backend contract. Block failed validation, unknown upstream, unbounded retries, incompatible config or absent tool/profile. NGINX reload applies configuration through its master process; runtime success still requires verification. [NGINX control](https://nginx.org/en/docs/control.html)

## Human-in-the-Loop

Show route/peer and exact configuration diff, affected clients, retry/connection risk, validation and rollback. One approval does not cover editing more routes or changing security behavior.

## Forbidden actions

`FORBIDDEN`: disable backend TLS checks, expose keys/config secrets, blanket debug logging, unlimited retries/timeouts, restart victims or arbitrary `nginx` shell invocation from the model.

## Evidence preservation

Save redacted peer/timing/error excerpts, config digest and paired probe observations before change; no full access-log dump or authorization headers.

## Verification

Three fresh post-change route/backend observations, then two 5-minute windows with meaningful traffic: configured error/latency objective, intended peers, no new upstream errors and stable backend resources. A direct backend-only success or config validation return is insufficient. Missing external vantage/traffic → provisional state and escalation.

## Rollback

Owner restores previous approved config digest and performs a validated reload; check it still references viable peers and compatible certificates. No automatic reload/rollback tool exists in current Argus.

## Escalation

Proxy/platform owner for route/config issues, backend owner for dependency failure, PKI for TLS. Attach peer/phase evidence, comparison limits and precise proposed correction. Stop after failed change or ambiguous action.

## Recording / memory

Common record plus virtual host/route, peer, proxy-versus-upstream status origin, timing phase and config digests.

## Prevention / follow-up

Predeploy route/syntax tests, structured upstream timing, bounded retry policy and monitored certificate/backend health.

## Lab validation

Disposable NGINX/backend: operator changes one upstream port to a closed test port for 90 seconds, then separately restores it and injects a backend delay exceeding the fixture read timeout. Expect RB-002/003 parent and RB-015 distinction between connection and read phases; zero automatic proxy/victim restart. Reject TLS-bypass or unvalidated reload proposal. Owner restores only the saved fixture config, verifies route and backend for two windows, and records all stages including approval/no-action. A direct-backend-success/incorrect-Host case must preserve uncertainty. Not executed.

## References

- [NGINX upstream module](https://nginx.org/en/docs/http/ngx_http_upstream_module.html), [proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html), [control](https://nginx.org/en/docs/control.html).

## Argus capability gaps

### Missing telemetry

Peer/route timing history, equivalent probe contract and config validation evidence.

### Missing tools

`get_proxy_upstream_history`, `validate_proxy_config`, TLS/deployment-history contracts.

### Tool improvements

Safe structured config fields, exact Host/SNI probe profiles and redacted upstream attribution.

### Detector improvements

Route-aware upstream error/timeout detector and policy-reviewed reload capability if added later.
