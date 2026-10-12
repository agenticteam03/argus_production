# Argus finished-product simulation

**Status: verified local prototype.** Open [`index.html`](index.html) in Chrome, Edge, Firefox, or Safari.
No installation, API, server, account, or internet connection is required. The entire experience, including the
21 source runbooks, is contained in that one file. You can copy it elsewhere and it still works.

This prototype previews Argus's intended incident-diagnosis and supervised-remediation experience from
[`brain/architecture/ARCHITECTURE.md`](../brain/architecture/ARCHITECTURE.md), version 1.8.6. It is separate from
the real read-only React client in `frontend/`. All infrastructure, alerts, identities, credentials, actions,
notifications, and tool results are simulated in browser memory. Reloading starts a new lab session.

## Try the complete workflow

1. Start on **Overview**. A stopped cache on `vm-166` has made `argus-lab-api` unhealthy. Two older externally
   resolved incidents provide history. The default demo identity is Alex Morgan, an in-scope human approver.
2. Open the active incident. Follow detection, runbook recall, bounded reads, checkpoints, and the diagnosis.
   Expand **Evidence** to see the host, executor, timestamp, redaction state, and real SHA-256 digest of each record.
3. Select **Review proposed action**. Inspect the frozen target identity, proposal digest, risk, expiry,
   evidence references, maximum action count, and rollback limitations. Approve one restart or deny it.
4. On approval, Argus rechecks current state, records one ledger attempt, simulates gateway dispatch, and waits
   for three distinct fresh observations. Only verified recovery closes the incident as `remediated`.
5. Inspect **Actions**, **Audit**, and **Decision history**. **Export evidence** downloads the full incident,
   observations, proposal, approval, action ledger, verification samples, and audit as JSON.
6. Select **Simulate failure** to start another scenario. Use **Lab operator: restore** to remove an injected
   fault externally. Argus records external resolution and cancels a pending action.

The overview clock supports pause and 1× / 2× / 4× speed. Approval expiry is five simulated minutes; investigation
and verification durations are compressed for exploration. **Reset lab** returns to the initial experience.

## Scenarios

| Scenario | Source | Behavior |
| --- | --- | --- |
| Cache dependency offline | SC-03 / RB-003 | Root cache, API victim; one supervised cache restart can be proposed |
| Worker OOM loop | SC-01 / RB-001 | Memory-boundary evidence; probable retention, no speculative restart |
| Worker non-OOM crash | SC-02 / RB-008 | Missing startup configuration; human follow-up |
| API health failure | RB-002 | Fixed evidence plan; distinguish victim from failed dependency |
| Database connection exhaustion | SC-04 / RB-004 | Identify leaking client; never restart the database victim |
| Host disk pressure | SC-05 / RB-005 | Confirm suspected writer from its own logs before diagnosing |
| CPU quota saturation | SC-06 / RB-006 | Distinguish container throttling from host saturation |
| Network isolation mismatch | SC-07 / RB-009 | Healthy backend on wrong network; no restart recommendation |
| Nginx upstream timeout | SC-08 / RB-015 | Slow upstream is root cause; proxy is victim |
| Unregistered alert | SC-09 | Fixed evidence pack, zero model calls, no diagnosis claimed |
| Stale telemetry | SC-10 / RB-014 | Refuse stale classification; escalate as `undiagnosable` |
| Malicious instruction in logs | SC-11 | Redact evidence and refuse untrusted control instructions |
| Investigation budget exhausted | SC-12 | Bounded stop and escalation; no unlimited retries |

For the cache scenario, choose gateway success, failure, lost response / indeterminate result, or successful
dispatch with failed recovery. Unknown and failed outcomes never trigger a second automatic attempt.

## Policies, identities, and console

**Policies** switches between read-only diagnosis and a supervised demo profile. The latter releases only
`(container.restart, vm-166/container:argus-lab-cache)` inside the simulation. Other remediations remain recommendations
for the owning human. Target holds block writes. Changing a policy, identity, or material evidence invalidates a
pending proposal. Repeated alerts correlate by host, target, class, and active episode instead of creating duplicate runs.

**Access & tokens** models viewer, operator, and approver roles; service and peer-agent identities; target scopes;
short-lived sessions; and token creation, expiry, and revocation. The public demo password is `argus-demo`.
Use the special identity buttons to test a nonhuman principal, an approver with only `vm-095` scope, or an expired session.
Out-of-scope incident evidence is hidden. Expired or revoked sessions require sign-in. Tokens are illustrative metadata,
not JWTs or real secrets; no session or token is written to cookies, local storage, or session storage.

**Console** accepts an explicit allowlist of simulated reads. Try `docker ps`, `docker stats`,
`docker inspect argus-lab-cache`, `docker logs --tail 20 argus-lab-api`, `df -h`, `free -m`, `uptime`, or `help`.
Mutating commands and shell chaining are refused and audited. Nothing is executed on your laptop or either VM.

**Runbooks** contains all 21 actual Markdown sources from `argus/runbooks/`, with their source versions and draft
status. The build embeds their content. Simulated use does not promote a draft runbook to production status.

## Architectural fidelity and limits

The simulation preserves deterministic classification, host-aware identities, bounded read tools, evidence hashing
and redaction, separation of victim and root cause, frozen proposals, human-only approval, precheck, an action ledger,
no-repeat handling of indeterminate actions, fresh post-action verification, and incident history.

Production Argus currently has **no released write capabilities**. This future-product preview does not change its
policy, API contracts, architecture, deployed services, or the existing frontend. The model reasoning, Postgres
transactions, LangGraph checkpoints, notification outbox, and action gateway are represented by deterministic state
transitions and audit records, rather than real integrations. There is no durable backend or genuine authentication.
The console and role controls demonstrate intended product boundaries; a browser-only mock is not a security boundary.

## Development and verification

The source is in `src/`; `index.html` is the generated portable artifact. Node 24+ and Python 3.12+ are sufficient;
there are no added package dependencies.

```powershell
python prototype/build.py
node --test prototype/tests/simulation.test.cjs
node prototype/tests/browser.cjs
```

The browser check uses installed Chrome or Edge in headless mode. Set `ARGUS_QA_BROWSER` to an installed Chromium
executable when it is elsewhere. QA screenshots, downloaded exports, and temporary browser profiles live in the ignored
`prototype/.qa/` folder. Browser checks cover offline startup, approvals, scope, session expiry, failure injection,
restoration, evidence and JSON export, audit, console refusals, token controls, runbooks, search, reset, responsive
navigation, and absence of runtime errors or external network requests.

If the repository runbooks change, run the build command again to refresh the embedded library.
