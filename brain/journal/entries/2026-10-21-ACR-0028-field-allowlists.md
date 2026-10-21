## 2026-10-21 — ACR-0028 proposed: field allowlists for the sensitive reads (OP-002 G-006)

Type: architecture
Who: conantkd (+ agent)
Context: OP-002 G-006 (data minimization) was the last gap without an owner. A read's `values` are, in 34 of 49
results, the gateway's JSON answer as it came; the dispatcher redacts patterns and declared literals but keeps every
field, and the model sees the values in each `<evidence>` tag. The gateways minimise at the source, with no check on
Argus's side.
Decision / result: [ACR-0028](../../architecture/changes/ACR-0028-field-allowlists.md) proposed: `allowed_fields` on
`CapabilitySpec`, required for every `READ_ONLY_SENSITIVE` read (13 today, after ACR-0026); the dispatcher keeps only
the declared paths before redaction, truncation and storage, and audits the names of the dropped keys; a canary test
per sensitive read. The initial lists come from the gateways' answers on `main`. Rejected: a deny list (fails open),
typed answer models (a new gateway field would turn into a failed read).
Consequences: one implementation PR after ACR-0026 merges; agent image only. Needs a second approval (secrets,
evidence integrity).
References: [OPEN_PROBLEMS](../../OPEN_PROBLEMS.md) OP-002, ACR-0026 (#210).
