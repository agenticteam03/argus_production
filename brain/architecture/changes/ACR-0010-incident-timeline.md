# ACR-0010 — A combined capability may read the current incident's own record (for `correlate_incident_timeline`)

| Field | Value |
|---|---|
| Status | `proposed` — accepted by a teammate's approval of its pull request; applied (ARCHITECTURE.md, code) in the implementation pull request |
| Proposed by | `conantkd` (+ agent) · 2026-10-13 |
| Accepted by | — |
| Second approval (safety principle only) | not needed (no safety principle is touched; see §4) |
| Architecture version | from `1.8.8` → `1.8.9` (with the implementation) |
| Task / PR | the last missing §12 capability, `analysis.timeline`; implementation PR to be opened after acceptance |

## 1. Detect and explain

§12 lists `correlate_incident_timeline` (`analysis.timeline`, Level 3, `argus_internal`): "combined; alerts, events,
stored evidence". It is the last §12 read capability not built (T-0036 to T-0040 built the others). A timeline needs
three sources: the incident's **alert occurrences** (when each alert fired and resolved), the target's **Docker
events** (start, die, oom, restart), and the incident's **stored evidence** (what was read, when, with which result).

Only the second is a read: §12.7 gives a combined capability **an invoker bound to `InvokeCapability`** with one
method, `read(name, target, arguments)`, and nothing else (`test_the_combined_impl_gets_no_executor` asserts it).
The alert occurrences and the stored evidence are in Argus's own store, which no capability can reach today.

## 2. Why the current architecture is insufficient

- §12.7 allows sub-reads only through `InvokeCapability`, which dispatches to executors (target services). There is
  no capability that returns the incident's own record, and making one ("read my incident's alerts" as a target read)
  would be a capability over Argus's database, outside the target model of §4.
- `knowledge.prior_incidents` (T-0039) reads the store through the in-worker `KnowledgeClient`, but returns OTHER
  closed incidents; a combined capability has no client at all, only the invoker.

## 3. Smallest reasonable change

**§12.7** — add after the first bullet:

> The invoker also offers **`incident_record()`**: a read-only, redacted view of the **current incident only** — its
> alert occurrences (alert name, fired / resolved times, disposition) and its stored evidence references (capability,
> target, status, `evidence_id`, collected time; no observation bodies). It takes no argument (no other incident can
> be named), is counted as one sub-call against `max_subcalls`, and is audited (`capability.incident_record`) like a
> sub-read. It never reaches an executor and never returns another incident.

**`analysis.timeline`** (`correlate_incident_timeline`, Level 3, in-worker, `max_subcalls` 3, container targets): one
`incident_record()` and one `container.events` sub-read of the target (the window from the first alert to now,
bounded to 120 minutes); the result is one time-ordered list (alerts fired / resolved, Docker events, reads made),
each line citing its `evidence_id` where it has one. Offered to no class until an evaluation batch measures it.

**Alternatives considered:**
- A: **a capability `incident.record`** dispatched like a read. Why not: a capability's target is a host or a
  container (§4); "the incident" is not an inventory target, and the policy, scope and executor model would need
  exceptions for it.
- B: **give combined impls the `IncidentMemoryPort`.** Why not: it could read any incident and write; the point of
  §12.7 is that a combined capability holds no more power than its sub-reads.
- C: **build the timeline from sub-reads only** (Docker events + restart history). Why not: without the alert times
  and the reads already made, it is not the incident's timeline, only the container's; that is `container.events`.
- D: **do nothing**: the model sees the evidence references in its context anyway. Why not as the end state: §12 lists
  the capability; but it is the cheapest choice if the team prefers to drop it from §12 instead.

## 4. Consequences

- **Code:** `_SubInvoker.incident_record()` (reads through the invocation context's incident id and the store
  `InvokeCapability` already holds; redacted; counted; audited); `analysis.timeline` spec and impl; policy entry.
- **Tests:** the record is the current incident's only; no bodies; counted against `max_subcalls`; audited; the
  timeline orders alerts, events and reads and cites evidence; `test_the_combined_impl_gets_no_executor` becomes
  `{"read", "incident_record"}`.
- **Safety principle?** No: read-only; no executor, no other incident, no observation bodies (only references), the
  redactor applied; host isolation unchanged (the `container.events` sub-read is policy-checked as before).
- **How to reverse it:** remove `incident_record` and the capability; §12.7 back to `read` only.

## 5. Decision

Proposed by `conantkd` on 2026-10-13. Options for the reviewer: accept as written; accept alternative D (drop
`analysis.timeline` from §12); or ask for another shape. Nothing is implemented before acceptance.

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§12.7, §12 Level 3 row), version 1.8.9, changelog line
- [x] journal entry (`journal/entries/2026-10-13-ACR-0010.md`)
- [ ] the implementation pull request
