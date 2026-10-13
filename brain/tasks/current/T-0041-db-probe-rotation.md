# T-0041 — `rotate-token.sh` rotates the `db_probe` token too

| Field | Value |
|---|---|
| Status | `in review` — script and tests done 2026-10-13; one real rotation on vm-166 after the merge (with the developer) |
| Phase | 13 — failure and recovery ("`db_probe` rotation is manual", T-0033) ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change |
| Branch | `task/T-0041-db-probe-rotation` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | the real rotation only (vm-166, then the agent's copy on vm-095) |

## Why it was manual

vm-166's Prometheus scrapes the db-probe's `/metrics` with the same token (`credentials_file`
`/etc/prometheus/secrets/db_probe_token`, mounted from `<secrets>/prometheus/`). Rotating only the service's copy
would have left Prometheus sending the old one: every scrape refused, and after 2 minutes a monitoring blind spot.

## Change

`rotate-token.sh db_probe`: both copies get the new token, each keeping its owner and mode, before `argus-v18-db-probe`
is recreated; a rollback restores both. Prometheus reads `credentials_file` at every scrape, so it needs no restart
(a scrape in between may be refused; the blind-spot alert waits 2 minutes). Without the Prometheus copy nothing is
changed. The agent's copy on vm-095 is replaced separately, as for the other executors (it re-reads it on its next
rejected read, T-0033).

## Tests

`tests/test_t0033_rotate_token_script.py`: 3 added (red seen: `db_probe` refused): both copies written and the right
service recreated, the token never printed; no Prometheus copy = no change; a rollback restores both.

## After the merge (with the developer, both leases)

On vm-166: `sudo sh /opt/argus-v18/app/ops/rotate-token.sh db_probe --as <who>`; then the agent's copy on vm-095
(as T-0033 step 2); check `up{job="argus-v18-db-probe"}` stays 1 and a `database.health` read succeeds.
