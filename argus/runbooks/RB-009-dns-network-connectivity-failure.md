# RB-009 — DNS/network connectivity failure

## Metadata

```yaml
id: RB-009
title: DNS/network connectivity failure
status: draft
owner: Argus Team
version: 1.0.1
created: 2026-09-29
last_reviewed: 2026-10-07
source_review_date: 2026-09-29
last_tested: 2026-10-07   # SC-07 lab run on vm-166, incident inc_21f900ee6139 (T-0018); still draft
detector: null
```

## Scope

Declared service endpoints/networks on Host T; record Docker network mode, source namespace, address family and endpoint contract. Exclude arbitrary discovery/scanning and host firewall administration. External-client failures require an actual external vantage. Apply [shared contracts](../RUNBOOK-CONVENTIONS.md); dedicated detection is missing.

## Incident definition

The configured source cannot resolve or complete the expected network interaction with a declared destination. DNS, routing, TCP, TLS and application responses must be assessed separately. Docker custom networks provide service-name resolution and network-specific reachability; inspect actual attachment. [Docker networking](https://docs.docker.com/engine/network/)

## User / service impact

Record affected source→destination edges and user routes. A nearby probe succeeding does not establish that the application can connect with its own network, resolver or credentials.

## Trigger / detection conditions

Proposed trigger: three failed bounded probes spanning at least `max(60 seconds, 2*S)` to one approved endpoint, or corroborated application resolution/connect errors with impact. Existing dependency/health detectors can supply a parent investigation, not a standalone network class. Timeout/missing probe data is not zero packet loss or successful resolution.

## Symptoms

NXDOMAIN/resolver errors, wrong address, connect timeout/refusal, intermittent connection failures, handshake errors and protocol-level failures.

## Plausible causes / hypotheses

H1 DNS record/resolver fault; H2 wrong network/route; H3 firewall/security policy; H4 absent listener/wrong port; H5 address-family or endpoint mismatch; H6 overload/socket exhaustion; H7 TLS/application issue despite working TCP; H8 faulty probe/vantage.

## Required evidence

Topology/version, source vantage, resolver answers/errors/time, expected address/port, network membership/routes, bounded TCP outcomes, listener state and application error. Preserve attempted IP/family; a hostname-only summary may hide one broken address among several.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `check_dns(name)` | Approved service-name resolution and addresses | `READ_ONLY_SENSITIVE` |
| `check_tcp_connection(host, port, attempts=3, timeout_s=2)` | Success ratio/errors, at most 5 attempts and 10 seconds each | `READ_ONLY_SAFE` |
| `check_http_endpoint(url, timeout_s=3)` | Allowlisted protocol check, no arbitrary redirect expansion | `READ_ONLY_SENSITIVE` |
| `get_container_network(container)` | Attachments, aliases, published ports | `READ_ONLY_SENSITIVE` |
| `get_socket_summary(container)` | Namespace socket states/listeners | `READ_ONLY_SENSITIVE` |
| `get_network_history(container, minutes=30)` | Traffic/error/drop trends, subject to missing-value defect | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Application-side network errors | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_route_diagnostics(source_id, endpoint_id)` from approved target namespaces, with route/interface and constrained policy metadata; `check_tls_endpoint(endpoint_id)` with hostname/SNI/chain/error; `get_external_probe_history(endpoint_id, minutes)` for the real client path. All require registry-owned destinations; routing/TLS metadata is `READ_ONLY_SENSITIVE`, sanitized probe history `READ_ONLY_SAFE`. DNS result, TTL/rcode, selected IP/family and resolver identity need tool extensions.

## Diagnostic workflow

| Step | Action / purpose | Interpretation / next step |
|---|---|---|
| 1 | Match error to declared edge and actual probe origin | Unknown edge/origin → insufficient_evidence. Known → 2. |
| 2 | DNS result against expected registry addresses | Missing/wrong answer → H1. Valid answer → 3; success from another resolver is counterevidence only for that resolver. |
| 3 | Inspect network membership and request route metadata | Wrong attachment supports H2. Missing route evidence leaves H2/H3 unresolved; proceed with bounded TCP check. |
| 4 | Connect to configured port; inspect listener/socket evidence | Refusal supports no listener or active rejection; timeout leaves filtering/routing/overload open. TCP success → 5. |
| 5 | TLS then expected protocol | TLS issue → RB-016; protocol/capacity failure → RB-003. Successful transport cannot clear these layers. |
| 6 | Correlate intermittent failures with family, traffic and socket states | Saturated sockets → RB-012; retries/overload → RB-021. Preserve missing/drop-query defect rather than trusting zero. |

## Decision tree

```text
DNS correct? no -> resolver/record
  yes -> source network/route correct? unknown -> missing route evidence
         TCP succeeds? no -> listener / policy / path / saturation
           yes -> TLS valid? no -> RB-016
                  protocol healthy? no -> RB-003
                    yes -> compare real client vantage or recovered incident
```

## Evidence interpretation

Blackbox supports HTTP/TCP/DNS probes but the module and vantage define what each result proves. [Blackbox Exporter](https://github.com/prometheus/blackbox_exporter) The existing Argus network history reports missing error-query results as zero: that output cannot establish absence of errors until fixed. Address-family differences and intermittent samples require multiple bounded observations.

## False positives and edge cases

DNS caches, TTL changes, load-balanced answers, split DNS, IPv6-only failures, proxy settings, asymmetric path, stale topology, probe connection load, firewall rejection versus missing listener and transport success with failed authentication.

## Diagnosis outcome

Allow all common outcomes. A probable layer failure includes source/destination/family and counterevidence; if refusal versus policy cannot be separated, retain both hypotheses. Fresh local success does not close an external-path failure.

## Mitigation

Network/service owner may restore the previous declared route/record or direct traffic to a tested alternate through an established procedure. No DNS/firewall mutation tool is available to Argus.

## Recovery

The affected source resolves and completes the intended protocol reliably, with service requests recovering. Restored DNS alone is only partial recovery.

## Root-cause correction

Correct service discovery/network attachment/listener or policy configuration, TLS settings or capacity, supported by the observed layer and reviewed by its owner.

## Action safety

DNS/route/firewall/restart changes are `MUTATING_HIGH_RISK` owner actions: require exact record/network/service and old/new values, ownership, protected management path, scoped blast radius and rollback. Block unknown namespace, broad rule flush, lost control-plane access, untested alternate or missing capability/profile. Read probes remain target-allowlisted and rate-bounded; HTTP redirects must not escape allowed destinations.

## Human-in-the-Loop

Approval names the exact change, source/destination, affected clients, propagation/TTL implications and rollback. It does not authorize a generic “repair network” command. Current Argus should escalate this change.

## Forbidden actions

`FORBIDDEN`: arbitrary scanning/traceroute/shell, global firewall/DNS flush, disabling TLS verification, injecting host entries blindly, fetching metadata/secret endpoints, or changing Docker networks without ownership checks.

## Evidence preservation

Retain bounded resolution/connect/protocol results, network config fingerprints and timestamps before a change; no broad packet captures or payload collection. Record probe source and family on every observation.

## Verification

Three distinct source-fresh results after completed change, then 5 minutes and at least one relevant configured DNS TTL where feasible. Expected resolution, TCP, TLS/protocol and application requests pass from affected vantage. Missing vantage/TTL coverage means provisional recovery plus follow-up; recurrence/timeouts escalate, not repeated network changes.

## Rollback

Owner retains previous record/network policy and a management path. Rollback propagation is not instantaneous; re-verify actual clients and treat rollback as an approved change. No automatic network rollback exists.

## Escalation

Network/DNS owner for early layers, service owner for listener/protocol, PKI for TLS. Attach exact edge, errors, families, timestamps and unresolved layer; request bounded route/actual-source evidence next.

## Recording / memory

Common record plus resolver, source namespace, attempted address/family, topology revision, propagation window and observed recovery path.

## Prevention / follow-up

Contract-test discovery/network changes, monitor client vantages/address families and implement scoped probes with unknown/error states.

## Lab validation

Disposable app-network pair: operator changes a fixture alias to a nonexistent name, then restores it and separately stops its listener; third case keeps TCP open but serves a protocol failure. Each fault lasts at most 2 minutes; topology and baseline are saved. Expect RB-003 parent→RB-009, DNS/listener/protocol distinction and zero victim restarts. A public/unknown endpoint and forged redirect must be refused. Denied config change produces no Argus action; operator restores exact fixture settings. Verify all layers, preserve the eight lifecycle artifacts, and replay absent error metrics to require unknown rather than healthy. Not executed.

## References

- [Docker networking](https://docs.docker.com/engine/network/), [Blackbox Exporter](https://github.com/prometheus/blackbox_exporter).
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — probe origin and network-history limitations.

## Argus capability gaps

### Missing telemetry

Source-equivalent route/policy, address-family/resolver details and external vantage.

### Missing tools

Shared route/TLS/external-probe contracts.

### Tool improvements

Fix missing-errors-as-zero; return chosen IP/family and source timestamps; enforce redirect destination policy.

### Detector improvements

Implement bounded layered probe trigger without treating protocol failures as transport failures; preserve RB-003 parent class.
