## 2026-10-20 — ACR-0026: one scheme of safety classes (OP-003)

Type: architecture
Who: conantkd (+ agent)
Context: OP-003 (open since 2026-09-30): §12.3 describes capabilities with `risk: low…very_high`, the code with a
two-value `safety_class`, the runbooks with the library's five classes. Phase 17 (`config/risk.yaml`, the action
cards) needs one answer first.
Decision / result:
- [ACR-0026](../../architecture/changes/ACR-0026-safety-classes.md) proposed and applied (ARCHITECTURE 1.8.22,
  §12.3 and §13.1): five classes, `READ_ONLY_SAFE`, `READ_ONLY_SENSITIVE`, `MUTATING_LOW_RISK`,
  `MUTATING_HIGH_RISK`, `FORBIDDEN`; `risk` is gone; `permission` and `side_effect` derive from the class;
  `FORBIDDEN` is never registered; the colour per target (ACR-0019) may only raise the class's minimum.
- Found while mapping: `container.detailed_logs` and `container.search_logs` returned log lines as
  `READ_ONLY_SAFE`, unlike `container.logs`. In review (`juanbetancurm`): `analysis.diagnostic_snapshot` carries
  `container.logs` lines, and `host.directory_sizes` returns names found on the host. All four are now
  `READ_ONLY_SENSITIVE`, and a combined read is as sensitive as its most sensitive sub-read (declared in `SUBREADS`,
  tested against the reads it makes). No runtime change (the lab profile allows both read classes).
- `tests/test_acr0026_safety_classes.py`: the registry follows the scheme; red seen on the old catalog.
- Needs a second approval (read-only).
Consequences: OP-003 is in progress. Left: the runbooks' "Safety class" column (54 rows in 19 runbooks differ from
the catalog) rewritten from it with a test; G-006's field allowlists for the sensitive reads; phase 17 adds the
`MUTATING_*` values to the code.
References: [OPEN_PROBLEMS](../../OPEN_PROBLEMS.md) OP-003, OP-002 (G-006), [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md) §3.7.
