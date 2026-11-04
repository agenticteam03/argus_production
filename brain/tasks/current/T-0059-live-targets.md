# T-0059 — Which inventory targets exist and run; Podman, systemd units and processes (ACR-0044)

**Status:** in review · **Owner:** conantkd (+ agent) · **Depends on:** —

## Goal

The investigation form lists only the inventory targets that are on their host, and Argus can watch and investigate an
application whether it runs in Docker, in Podman, as a systemd unit or as a plain process, as
[ACR-0044](../../architecture/changes/ACR-0044-live-targets.md) designs.

## Done in this task

1. A presence contract: `argus_target_present` / `argus_target_up` per declared target; the exporter says it for
   containers; signals `target_present`, `target_up` (`$kind`). The map's `presence` (a stopped container no longer
   reads as running), `GET /api/v1/targets` `state`, the form hides `absent` targets unless asked.
2. Podman: `ARGUS_CONTAINER_SOCKET` in a host's env file (read gateway, exporter, action gateway).
3. The host probe watches systemd units (cgroup) and declared processes (`comm` or `pidfile`): its token-protected
   `/metrics`, `services/<unit>/status`, `processes/<name>/status`; the inventory's `process` kind and validation; the
   rendered allowlists; each Prometheus scrapes it with its token.
4. `service.status` and `process.status` (Level 1, offered to no model class); class `target_down` (RB-023,
   `evidence_pack`); alert `TargetDown`; the alert intake names a service or process target from `kind` / `name`.

## Not in this task

- The deploy (a separate DEPLOY task with both leases; ACR-0044 §4 gives the order, including the host-probe token copy
  for Prometheus).
- Declaring real units or processes in `config/inventory.yaml`: none is declared yet; the lab has none to watch.
- Offering the two reads to a model class (a separate change with its model batch, ACR-0024 §3.8).
- A unit's restart count and exit status (D-Bus or the journal; RB-023 "Missing tools").
