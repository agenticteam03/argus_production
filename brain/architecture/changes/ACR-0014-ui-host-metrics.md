# ACR-0014 — Bounded host metrics in the public UI

| Field | Value |
|---|---|
| Status | `proposed` — request review in PR #151 before merge |
| Proposed by | conantkd (+ agent) · 2026-10-14 |
| Accepted by | pending |
| Second approval (public edge / host isolation) | pending independent team review in PR #151 |
| Architecture version | 1.8.11 → next free version when accepted |
| Task / PR | T-0016 · PR #151 |

## 1. Detect and explain

Observed in PR #151: the Dashboard's Agent status card receives `health: null` from the real HTTP adapter, and
`askAgent` returns a fixed placeholder. The suggested “Check Host T memory usage” therefore cannot return a reading.
The existing MetricsPort and `config/signals.yaml` already provide host CPU busy, available-memory and root-disk
ratios from Prometheus, with a freshness gate. The public UI contract has no route for those values.

## 2. Why the current architecture is insufficient

§7.1 lists no authenticated metric read route, and §7.1's public edge proxies only the contract routes. The only
`/metrics` route is a private Prometheus exposition and must remain private. T-0016 explicitly anticipates a read
route over the inventory and latest signals for its later visual-map level. ACR-0012 §3.1 row 7 left free-text chat
as a placeholder; it did not authorize a browser to submit arbitrary PromQL or model requests.

## 3. Smallest reasonable change

Add `GET /api/v1/host-metrics` to §7.1 and to the public UI contract/edge allowlist, available to any authenticated
role with a read or investigate token. The API, not the browser, enumerates inventory host targets and asks
MetricsPort only for `host_cpu_busy_ratio`, `host_memory_available_ratio`, and `host_disk_used_ratio`. The response
has host reference, sample time, availability and the three 0–1 ratios. Missing, stale, non-finite or out-of-range
values become `null`; one host's monitoring outage does not hide the other host. No request parameters, PromQL,
exporter address, credentials, evidence or raw telemetry are exposed. The existing 30-second dashboard poll and
edge GET rate limit apply; the API shares one snapshot across authenticated viewers for 20 seconds, bounding normal
traffic to six named signal reads and two freshness checks per cache refresh.

The frontend presents the values for Host A (`vm-095`) and Host T (`vm-166`) and answers bounded CPU/memory/disk
questions from the same endpoint. An explicit “Investigate Host T” uses ACR-0012's existing
`POST /api/v1/investigations` with `request_kind=check`, subject to `/me`, role and quotas, and links to the queued
incident. This is a deterministic UI command, not general free-text conversation or a claim of completed diagnosis.

**Exact architecture edit after acceptance:** in §7.1 add a table row:

> `GET /api/v1/host-metrics` | named host metric snapshot | JWT, any role | Inventory host targets only;
> fixed CPU busy, memory used and root-disk used ratios; sample time; missing is null; no PromQL parameter (ACR-0014).

In §7.1's public-edge paragraph include this authenticated GET among the contract allowlist; add a changelog row
for the next free version. Do not change the private `/metrics` route or the `MetricsPort` contract.

**Alternatives considered:**

- Reuse `/metrics` in the browser: rejected because it exposes private operational telemetry and is not a UI API.
- Ask Prometheus directly from the browser: rejected because it exposes its address and bypasses Argus auth and
  the inventory/signal allowlist.
- Continue the placeholder card: cannot answer the requested operational question.
- Start a full investigation for every metric question: costly and asynchronous when a bounded read suffices.

## 4. Consequences

- Code: one authenticated API route, one exact edge location, UI contract/sample, frontend card and bounded chat.
- Tests: auth, missing/stale values, no invented numbers, contract and edge allowlist, frontend adapter and parser.
- Deployment: a new API + UI image on vm-095 after PR approval and VM lease; no VM action in this PR's preparation.
- Risk: an authenticated public client can cause repeated Prometheus reads. A 20-second API cache and existing
  edge per-address limits bound normal traffic; the reviewer should assess load before deployment. Host resource percentages are
  visible to all existing viewer accounts. No raw Prometheus query, secret, exporter or tunnel address leaves Argus.
- Reversal: remove the new edge location and UI call; the private `/metrics` and investigation flow remain intact.
- Safety principle: **yes**, the public edge's read surface and host telemetry boundary widen. An independent team
  review is required before merge. The existing write gate remains closed.

## 5. Decision

Pending: review and acceptance in PR #151. The implementation is included for concrete review, but the architecture
specification must not be edited or the PR merged until the ACR is accepted.

## 6. Applied

- [ ] ACR accepted and `ARCHITECTURE.md` updated with a version/changelog entry.
- [x] Implementation and contract in PR #151 for review.
- [x] Task and journal entry in the same PR.
