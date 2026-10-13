## 2026-10-13 — E2E-8 step 1: SC-10, SC-12 and the identity proof in the runner's catalogue

Type: feature
Who: conantkd (+ agent), on `juanbetancurm`'s E2E-8 plan
Context: Phase 12 needs five runs of every scenario through `ops/e2e/run.py`; SC-10, SC-12 and the identity proof
were not in the catalogue (they stop Argus's own services or need two hosts at once).
Decision / result:
- The runner takes commands and gates on another host (`{host: ..., run: ...}`, gate `host:`), lists of gates, and
  several investigations per run, sent together and each graded; every touched host must be in `hosts`.
- SC-10 stops vm-095's `argus-v18-node-exporter` (the `monitoring_blind_spot` class of T-0027), not the gate exporter
  of the LGS run (that one ends `undiagnosable` before any class). SC-12 stops vm-166's read gateway during SC-01's
  loop: escalated, never `diagnosed`, and vm-095 still answers. ID-1 runs SC-01 and SC-02 together through YAML
  anchors. Their reset starts the stopped service first.
- `on:` was the first key name for a command's host: PyYAML (YAML 1.1) reads it as `true`; renamed `host:`.
Consequences: no VM change; the runs (E2E-8 step 2) need both leases.
References: `ops/e2e/run.py`, `ops/e2e/scenarios.yaml`, `tests/test_e2e8_catalogue.py`.

### Test state

`tests/test_e2e8_catalogue.py` 11 (red seen), `tests/test_e2e_runner.py` 39 unchanged, green.

### Next step

E2E-8 step 2 (both leases): `ops/e2e/run.py H-1 H-2 SC-09 SC-11 --runs 5`, then `ops/e2e/run.py SC-10 SC-12 ID-1
--runs 5`; read every miss.
