# T-0042 — Escalation routing as data (`config/routing.yaml`, §15.2)

| Field | Value |
|---|---|
| Status | `in review` — code done 2026-10-13 |
| Phase | 8 — policies ("routing data", [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change (no ACR): §15.2 and §4 ("`routing.yaml` escalation routing per class family") as written |
| Branch | `task/T-0042-routing` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | no (code; on vm-095 with the AFTER-MERGE) |

## Design

- `argus/policy/routing.py` (`Routing`, imports nothing from Argus): `default`, `by_family`, `by_alertname`; a target
  is `channel:<name>` or `peer:<name>` (§23). Order: the unsupported alert's name, then the class family, else the
  default. Fail closed: an unknown key or family, a malformed target or no default refuses the file at startup.
- `config/routing.yaml` (new): `default: channel:operators`, empty maps — today every escalation goes to the
  operators, as before; the file is where a team or a peer agent gets its share.
- The runner's escalation notification (`<incident>:escalation`, the outbox, unchanged key) now carries `route`. The
  alert name comes from the incident's first alert occurrence; the family from its class.
- No file = the default route (older checkouts keep working).

## Tests

`tests/test_t0042_routing.py`, 10 (red seen: no `route` in the notification): the shipped file; the precedence; five
malformed files refused; an unsupported escalation's notification names `channel:operators`; a class follows its
family.
