# T-0039 — `query_prior_incidents`: has this happened here before?

| Field | Value |
|---|---|
| Status | `in progress` — #123 merged; on both VMs since the AFTER-MERGE to `main` `ad72617` (#132, 2026-10-13); next: offer to a class, with evaluation cases |
| Phase | 4 / 9 — Level 3 capabilities ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change (no ACR): §10.5 ("a strategy may request more through … `knowledge.prior_incidents`") and the §12 Level 3 row, as written |
| Branch | `task/T-0039-prior-incidents` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | no (code only; verified after the merge) |

## Design

- `knowledge.prior_incidents` / `query_prior_incidents`: Level 3, `READ_ONLY_SAFE`, executor `argus_internal`, runs
  in the worker, `max_per_incident` 2, tag `prior_incidents` (offered to no class until measured).
- Args: `incident_class` (must be a registered class, else `invalid_args`), `k` 1–5.
- Reads `IncidentMemoryPort.similar_incidents(target, class, k)` (both stores already had it for §10.5 recall):
  **closed** incidents of the **same target** only (host isolation: the same container name on the other host is
  another target), newest first. The open incident being investigated is never its own precedent.
- Each: date, outcome, confidence, root-cause target, diagnosis cut to 300 characters, up to 3 findings. The answer
  goes through the redactor like every observation.
- `KnowledgeClient(knowledge, memory)`: the worker's wiring gives it the store; without one the read is
  `unreachable`, never empty.

## Tests

`tests/test_t0039_prior_incidents.py`, 7 (red seen: no capability): spec and policy; same target and class, newest
first, not the other host's twin, not the open one; none found said plainly; the diagnosis cut and `k` bounded; an
unknown class refused; no memory = unavailable; the worker's wiring gives the client the store.
