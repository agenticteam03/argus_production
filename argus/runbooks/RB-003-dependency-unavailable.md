# RB-003 — Dependency unavailable

## Metadata

```yaml
id: RB-003
title: Dependency unavailable
status: draft
owner: Argus Team
version: 1.1.0
created: 2026-09-29
last_reviewed: 2026-10-28
source_review_date: 2026-09-29
last_tested: null
detector: dependency_unavailable
actions:
  - action: container.start
    target_role: root_cause
    service_role: cache
    when: 'state == "exited" or state == "created"'
    rationale: A stopped cache dependency may be started after its own status is confirmed.
  - action: network.restore
    target_role: root_cause
    service_role: api
    when: 'state == "running"'
    rationale: A running api that is attached to a network it does not declare may be put back on its declared network, after its own status and the dependent's broken link are confirmed.
```

## Scope

Declared dependencies of Docker/Compose services on Host T. Probe from the affected application network; the existing network probe is nearby, not inside the application's exact namespace. Record Docker/network version, endpoint contract, TLS mode and PostgreSQL major where relevant. Exclude undeclared Internet targets and service discovery guesses. [Common contracts](../RUNBOOK-CONVENTIONS.md) apply.

## Incident definition

A declared dependency cannot complete its expected interaction from the affected service path. Dependency state, network reachability, protocol admission and capacity are different layers. A failure observed only from Host A does not establish Host T application connectivity. Docker network attachment and DNS behavior depend on network configuration. [Docker networking](https://docs.docker.com/engine/network/)

## User / service impact

Map failed transactions/routes to dependency edges. Several failing frontends may share one dependency. Observe partial functionality and cache behavior; do not infer a total outage from one failed dependency check.

## Trigger / detection conditions

Existing detector selects `dependency_unavailable` when a fresh `dep.<name>.up` or `dep.<name>.accepting` is false. It has no sustained-duration condition. Proposed alert duration: two scrapes or 60 seconds, calibrated to the service; high-impact failures start immediate investigation. A missing dependency series is unknown, not up. Unsupported dependencies need topology and detector work before automated routing.

## Symptoms

Resolution errors, connection refusal/timeouts, handshake/authentication failures, protocol errors, database admission failure, upstream timeouts and cascading health failures.

## Plausible causes / hypotheses

H1 wrong/missing DNS record; H2 network attachment/route/firewall fault; H3 listener/service down; H4 TLS or authentication mismatch; H5 capacity exhausted by legitimate load, leaking client or retry storm; H6 dependency internal failure; H7 probe misconfiguration/staleness. Multiple failing layers can coexist.

## Required evidence

Declared source/target/protocol and expected route, both identities, DNS answer and error, target-network reachability, listener/protocol results, capacity and internal health, victim error, client/load history and correlated changes. Compare source vantage explicitly before treating disagreement as contradiction.

## Required Argus tools

Existing contracts, if published and allowed:

| Tool / input | Purpose / relevant output | Safety class |
|---|---|---|
| `check_connectivity(container)` | Dependency DNS/TCP matrix from app-net probe | `READ_ONLY_SENSITIVE` |
| `check_dns(name)` | Resolution status and addresses for approved name | `READ_ONLY_SENSITIVE` |
| `get_container_network(container)` | Network attachment, DNS aliases and ports | `READ_ONLY_SENSITIVE` |
| `check_tcp_connection(host, port, attempts=3, timeout_s=2)` | At most 5 connects; success ratio, latency, errors | `READ_ONLY_SAFE` |
| `check_http_endpoint(url, timeout_s=3)` | Exact allowlisted HTTP response and latency | `READ_ONLY_SENSITIVE` |
| `get_container_status(container)` | Dependency process/health and identity | `READ_ONLY_SENSITIVE` |
| `inspect_database_health(container)` | PostgreSQL states, capacity, waits; monitor view only | `READ_ONLY_SENSITIVE` |
| `get_db_connection_history(database, minutes=30)` | Client-group connection trends | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Victim/dependency protocol error context | `READ_ONLY_SENSITIVE` |
| `correlate_incident_timeline(container, minutes=30)` | Related error/event chronology; not causal proof | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_route_diagnostics(source_id, endpoint_id)` returns approved route/interface/error metadata without arbitrary host input, `READ_ONLY_SENSITIVE`; `check_tls_endpoint(endpoint_id)` returns SNI/chain/time validation, no keys, `READ_ONLY_SENSITIVE`; `check_database_admission(database_id, role_profile)` uses a preconfigured ordinary-role credential in the probe, returns a sanitized connection result and source time, `READ_ONLY_SENSITIVE`. Existing TCP and count-based database flags do not implement these contracts.

## Diagnostic workflow

| Step | Action / why | Interpretation and next step |
|---|---|---|
| 1 | Bind victim/dependency edge and fresh trigger | Wrong target or obsolete topology → correct selection/escalate. Known edge → 2. |
| 2 | Resolve exact declared name from app-network probe | DNS failure → H1/RB-009. Valid but unexpected answer → configuration/ownership investigation. Correct answer → 3. |
| 3 | Compare attachments and bounded route evidence | Wrong network/route supports H2. Probe lacks actual namespace equivalence → record limitation. Continue with 4; do not claim route is good just because no tool exists. |
| 4 | Connect to expected port; inspect dependency state | Refusal suggests listener/path rejection; timeout cannot distinguish filtering from overload. TCP success → 5, not “dependency healthy.” |
| 5 | Verify TLS where used, then configured application protocol/admission | Certificate failure → RB-016. Auth failure → owner correction. HTTP/database error → 6. Never disable TLS verification. |
| 6 | Read capacity/internal state and client trends | PostgreSQL slot pressure → RB-004; lock wait → RB-013; storage → RB-019. Error with spare capacity → dependency logs/config owner. |
| 7 | Compare timing and victim errors; identify supported failing layer | The earliest symptom is a hypothesis lead. If several layers remain unexplained, record multiple hypotheses; choose no speculative write. |

## Decision tree

```text
DNS -> network/route -> TCP -> TLS if used -> protocol -> capacity -> internal health
 fail     fail         fail      fail          fail        fail          fail
RB-009  RB-009      listener/  RB-016       auth/config  RB-004/     dependency
                    path                   /service     RB-013      owner
```

Stop at the first demonstrated failure to avoid unnecessary higher-layer probes, but inspect downstream failures if new evidence indicates multiple faults. No failed layer authorizes restarting the victim.

## Evidence interpretation

TCP establishes transport acceptance only. PostgreSQL can reserve slots for privileged roles; monitor success does not establish normal client admission. [PostgreSQL 16 connection settings](https://www.postgresql.org/docs/16/runtime-config-connection.html)

Application errors plus a matching failed layer support dependency attribution. A healthy nearby probe weakens a global outage but cannot exclude client-specific credentials, namespace or policy faults.

## False positives and edge cases

DNS caching/round robin, IPv4/IPv6 differences, wrong port, split network namespaces, reserved monitoring slots, probes with different credentials, failover, stale topology, shared dependency labels and clock skew. Connection attempts are bounded to avoid amplifying overload.

## Diagnosis outcome

Use `probable_root_cause` with failing layer and evidence; otherwise `multiple_hypotheses` or `insufficient_evidence`. Permit `incident_no_longer_present` only with fresh dependency and victim success; `wrong_runbook` when the dependency is healthy and the local application is defective.

## Mitigation

Coordinate dependency-owner containment, backoff or controlled load reduction. These are operator procedures or separately gated extensions. Argus must not restart the incident's dependent service under RB-003.

## Recovery

The dependency accepts the intended protocol under normal credentials and representative demand; victims then recover without forced reconnect storms. Verify both layers independently.

## Root-cause correction

Repair DNS/network/TLS/config, connection management, capacity or dependency defect according to the supported branch. A temporary pause/failover does not prove the defect was fixed.

## Action safety

Any dependency restart/stop/reconfiguration is `MUTATING_HIGH_RISK` and belongs to its owning runbook and separately authorized target. Require exact target/ID, diagnosed mechanism, capacity/replication assessment, protected-service policy and rollback. Default here is read-only/escalate. Existing lab stop/session actions are not permission to act on arbitrary clients. Block victim restart even if a model proposes it; block writes with unknown owners, absent predicates, unresolved shared impact or unavailable audit.

## Human-in-the-Loop

For an action proposed by the owning runbook, show dependency and victims, exact arguments, expected capacity benefit, transaction/request risk and source evidence. All writes need the shared frozen-proposal gate; no approval for “fix connectivity” as an open-ended task.

## Forbidden actions

`FORBIDDEN`: restart dependent services to free dependency capacity; scan arbitrary ports; flush firewall/DNS broadly; reveal credentials; bypass TLS; arbitrary SQL/session termination; switch to Host A probes and claim equivalent evidence.

## Evidence preservation

Save topology version, source vantage, protocol errors, resource/client history and paired dependency/victim snapshots before an owning-runbook action. Preserve redacted refs rather than packet payloads or secrets.

## Verification

After action/operator-change completion, require fresh DNS/TCP/TLS/protocol results as applicable, ordinary-role admission for databases, plus victim endpoint recovery. Three distinct post-action samples, then 5 minutes without renewed failures or growing retry pressure. An unobservable TLS/admission layer limits closure. Timeout or recurrence escalates; no automatic victim restart. Record externally resolved incidents separately.

## Rollback

This runbook performs no default write. The dependency owner must retain the previous network/config/deployment state and define its restoration before a change; rollback itself needs approval and must not knowingly restore harmful load.

## Escalation

Network owner for DNS/route/TCP; PKI owner for TLS; DBA for capacity/protocol; application owner for client-specific failures. Stop at read budget, missing vantage or unverified identity. Attach failing layer, counterevidence, affected graph, timestamps and next missing probe.

## Recording / memory

Common record plus source network, dependency edge, layer results, client-role profile, victim protection decision, missing capabilities and recovery of each victim.

## Prevention / follow-up

Maintain topology and protocol probes, bounded pools/backoff, dependency capacity budgets and client-vantage tests. Treat a shared outage as correlated incidents, preserving separate evidence.

## Lab validation

Disposable API/PostgreSQL pair: sequentially inject (A) a wrong declared DNS name, (B) a closed test listener, (C) valid TCP with exhausted ordinary connection slots. Capture baseline and restore each fault before the next; cap each at 5 minutes. Expect RB-003, layer-specific evidence and H1/H3/H5; C branches to RB-004. Assert zero victim restarts, refusal of unknown target/port and no action on expired approval. Operator fixes the exact fixture; observe fresh dependency admission and API recovery for 5 minutes, then record all eight lifecycle stages. Replay a successful privileged probe while ordinary admission fails: do not close. Tests remain unexecuted.

## References

- [Docker networking](https://docs.docker.com/engine/network/) — network and name-resolution context.
- [PostgreSQL connection settings](https://www.postgresql.org/docs/16/runtime-config-connection.html) — admission and reserved slots.
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — probe origin and policy boundaries.

## Argus capability gaps

### Missing telemetry

Actual source-namespace equivalence, TLS/admission and route evidence.

### Missing tools

`get_route_diagnostics`, `check_tls_endpoint`, `check_database_admission`.

### Tool improvements

Label transport-only checks accurately; distinguish calculated DB acceptance from observed admission; propagate composite errors and source times.

### Detector improvements

Sustained/role-aware dependency failure, missing-series handling, topology validation and deterministic victim protection across all proposal paths.
