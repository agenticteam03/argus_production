# RB-016 — TLS certificate / handshake failure

## Metadata

```yaml
id: RB-016
title: TLS certificate / handshake failure
status: draft
owner: Argus Team
version: 1.0.2
created: 2026-09-29
last_reviewed: 2026-10-09
source_review_date: 2026-09-29
last_tested: null
detector: tls_failure
```

## Scope

Registered HTTPS/TLS endpoint profiles, including NGINX edge and backend TLS. Record client/server versions, SNI/hostname, trust-profile identifier, mTLS requirement and source clock. OpenSSL 3.0 documentation is a reference, not an assumption about every deployed TLS stack. [Common contracts](../RUNBOOK-CONVENTIONS.md) apply; dedicated TLS detection is absent.

## Incident definition

A configured client cannot establish its required authenticated TLS session. Certificate validity, hostname identity, trust path and negotiation are separate checks. A completed handshake without verification is not proof of authenticated connectivity. [OpenSSL verification](https://docs.openssl.org/3.0/man1/openssl-verification-options/)

## User / service impact

Measure affected hostnames/client cohorts and route failures. Different clients may use different trust stores or cached/resumed sessions; one successful client does not establish universal recovery.

## Trigger / detection conditions

Proposed incident trigger: repeated strict TLS failure from an approved client profile over `max(60 seconds, 2*S)`, correlated with user/service failure. Expiry warning at a configurable renewal lead time (lab 14 days) is preventive, not proof of current outage. Unknown certificate time or local clock invalidity requires uncertainty, not renewal as an automatic conclusion.

## Symptoms

Expired/not-yet-valid certificate error, hostname mismatch, unknown issuer/incomplete chain, unsupported negotiation, mTLS rejection or proxy upstream handshake failure.

## Plausible causes / hypotheses

H1 expired certificate; H2 wrong hostname/SNI or certificate binding; H3 chain/trust-store mismatch; H4 protocol/cipher policy mismatch; H5 missing/invalid client authentication; H6 backend TLS misconfiguration; H7 source/server clock error; H8 wrong destination/DNS or transport failure.

## Required evidence

Exact sanitized verification/handshake error, endpoint/IP/port and expected hostname, configured SNI/trust/client profile, public certificate fingerprint/SAN/validity/issuer metadata, chain verification result, clock quality, deployment/renewal time and transport success. Never collect private keys, full credential config or client certificate secrets.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `check_dns(name)` | Establish destination addresses | `READ_ONLY_SENSITIVE` |
| `check_tcp_connection(host, port, attempts=2)` | Establish bounded transport result and latency | `READ_ONLY_SAFE` |
| `check_http_endpoint(url, timeout_s=3)` | Approved HTTPS request; inspect whether its configured verification matches client contract | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Redacted handshake phase/errors | `READ_ONLY_SENSITIVE` |
| `inspect_service_config(container, config='main')` | Only allowlisted non-secret TLS directive metadata | `READ_ONLY_SENSITIVE` |

HTTP tool success is insufficient when trust/SNI/verification policy is not exposed. Current tools do not supply a complete certificate-validation report.

## Missing tools

**MISSING TOOL REQUIREMENT:** `check_tls_endpoint(endpoint_id)` uses a fixed registered hostname/SNI/trust/optional mTLS profile, returns strict verification, negotiated protocol, public fingerprint/SAN/validity and bounded errors; `get_certificate_deployment(service_id)` exposes fingerprint and renewal/reload history only. Both `READ_ONLY_SENSITIVE`. Shared `get_time_sync_status(host_id)` supplies source clock quality. No tool accepts key paths, arbitrary CA imports or a `verify=false` argument.

## Diagnostic workflow

| Step | Action / why | Interpretation / next step |
|---|---|---|
| 1 | Verify exact destination and DNS/TCP | Transport failure → RB-009. Correct listener → 2. |
| 2 | Strict TLS check with actual client profile | Record failed phase; missing tool/profile → insufficient_evidence, not insecure fallback. |
| 3 | Compare hostname/SNI and served certificate metadata | Wrong binding/SAN → H2/H8; correct identity → 4. |
| 4 | Compare validity and trustworthy current time | Expired under good clock → H1; inconsistent clocks → RB-020/H7. |
| 5 | Inspect chain/trust and negotiation/mTLS results | H3/H4/H5; client secrets stay in probe. Distinguish edge and upstream TLS legs. |
| 6 | Compare certificate deployment/reload fingerprints | New file but old served certificate → owner deployment investigation; do not assume reload occurred. |
| 7 | Preserve public metadata, owner correction, strict fresh verification | No diagnosis based only on generic “SSL error.” |

## Decision tree

```text
transport works? no -> RB-009
  yes -> strict TLS profile fails where?
           name/SNI -> binding/destination
           time -> validity + clock verification
           chain/trust -> issuer/client trust profile
           negotiation/mTLS -> version/policy/client-auth owner
           upstream only -> NGINX backend TLS branch
```

## Evidence interpretation

SNI selects the intended server identity; hostname validation and certificate-chain verification must still be performed. Diagnostic clients can continue despite verification errors unless configured to fail appropriately; a tool must return the strict verdict, not merely socket completion. [OpenSSL client diagnostics](https://docs.openssl.org/3.0/man1/openssl-s_client/)

## False positives and edge cases

Wrong client clock, missing SNI, IP probe of a DNS certificate, stale load-balanced peer, resumed session, old client trust store, mixed certificate rollout and distinct proxy/client trust policies.

## Diagnosis outcome

All common outcomes allowed. Probable cause identifies failing TLS leg/profile and exact verification evidence; unknown clock or trust policy keeps alternatives open. Approaching expiry alone is follow-up, not current handshake diagnosis.

## Mitigation

PKI/service owner deploys a valid existing certificate/chain or corrects binding through the approved certificate pipeline. An alternate endpoint must preserve the required authenticated identity. No security downgrade is a mitigation.

## Recovery

Fresh strict handshakes and application requests succeed for affected profiles and peers; intended public fingerprint is served and renewal margin satisfies policy.

## Root-cause correction

Repair renewal/distribution/reload automation, hostname inventory, trust lifecycle or mTLS ownership; correct clock fault separately. NGINX TLS configuration must match its installed build and served identity. [NGINX SSL module](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)

## Action safety

Certificate deploy/reload, trust/policy or time changes are `MUTATING_HIGH_RISK`. Require exact endpoint/fingerprint/profile and compatible key reference managed outside model context, owner approval, validated config and previous still-valid rollback artifact. Block untrusted issuer addition, expired/revoked rollback, mismatched identity, absent tool or unknown client blast radius. Current Argus has no certificate mutation capability.

## Human-in-the-Loop

Show public metadata and validation failures, exact deployment/config revision, affected clients and rollback limits. Approval never permits exposing key material or turning verification off.

## Forbidden actions

`FORBIDDEN`: `verify=false`/insecure TLS bypass, retrieve keys/PEM secrets, import arbitrary CAs, downgrade protocol policy, reuse expired/revoked certificates or alter clocks to make an expired certificate appear valid.

## Evidence preservation

Save bounded public certificate metadata/fingerprint, verification reason, time-quality evidence and endpoint profile version. No private-key paths/content, session secrets or TLS key logs.

## Verification

Three new strict connections after deployment completion across the affected approved peers/profiles, then 5 minutes of successful real-route probes. Confirm correct fingerprint/name/chain/time and acceptable expiry margin. Resumed sessions or a single peer cannot verify all replaced certificates. Missing profiles, recurring errors or unknown source time prevents closure.

## Rollback

Owner may restore only an approved still-valid, unrevoked and identity-correct previous certificate/config. Otherwise forward repair is required. Every reload/rollback is separately reviewed; no automatic TLS rollback tool exists.

## Escalation

PKI/security owner plus service/proxy owner; platform for clock faults. Attach public metadata, exact profile/leg, verification error and missing evidence. Stop if resolution would require a security downgrade.

## Recording / memory

Common record plus endpoint profile, public fingerprint, failed validation category, client cohort, time confidence and renewal follow-up; never store keys.

## Prevention / follow-up

Renewal lead-time alerts, strict multi-profile probes, certificate inventory, tested reload and public-fingerprint monitoring.

## Lab validation

Private disposable test CA/server with synthetic hostnames: serve (A) expired certificate, (B) wrong SAN, (C) incomplete chain, restoring the fixture between cases. Do not change workstation time or use production keys. Expect proposed/unsupported TLS trigger, distinct errors or insufficient_evidence if strict tool unavailable. Reject verify-off and key-reading proposals. Owner deploys the valid fixture certificate; test denial then approved owner change, fresh strict handshakes and application recovery for 5 minutes, with all lifecycle artifacts. Replay bad client-clock metadata to require RB-020 investigation. Not executed.

## References

- [OpenSSL verification](https://docs.openssl.org/3.0/man1/openssl-verification-options/), [client diagnostics](https://docs.openssl.org/3.0/man1/openssl-s_client/), [NGINX TLS](https://nginx.org/en/docs/http/ngx_http_ssl_module.html).

## Argus capability gaps

### Missing telemetry

Strict TLS profile/result, public certificate deployment history and clock-quality evidence.

### Missing tools

`check_tls_endpoint`, `get_certificate_deployment`, `get_time_sync_status`.

### Tool improvements

Expose HTTPS verification/SNI/trust provenance without secrets; support registered client profiles with no bypass flag.

### Detector improvements

Separate expiry warning from handshake incident; clock-aware, per-peer/profile detection and scope permissions.
