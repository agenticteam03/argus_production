# ACR-0022 — More autonomous investigation: open investigations, follow-up checks, new reads, curated and isolated knowledge

Part of the next-phase proposal ([task](../../tasks/current/NEXT-PHASE-supervised-remediation.md)), from `conantkd`'s
"Argus actúa" (sections 4.6, 5.7, 8 and ACR "H") and this proposal's notes. **Reads and suggestions only:** nothing in
this ACR writes to a target, and nothing here can be the basis of an executed action except the curated reference
corpus (ACR-0019 §3.5). ACR-0021 is T-0045 (the UI backend specification).

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm and conantkd (+ agents) · 2026-10-18 |
| Accepted by | pending (team review of the NEXT-PHASE proposal PR) |
| Second approval (safety principle only) | **required**: secrets (a new outbound path for research), evidence integrity (new evidence kinds); rule 7 is kept |
| Architecture version | the next free version when applied |
| Task / PR | NEXT-PHASE · PR #170 |

## 1. Detect and explain

Argus investigates only what a registered class covers, and only when triggered:
- an incident that matches no class ends with the fixed evidence pack and an escalation (§1.3, `unsupported_escalated`;
  OD-15 "a diagnosis-only mode for unsupported reports" is off);
- after a human fixes something (by hand, or later through an approved action) nothing re-checks automatically;
- the reads cannot answer "what changed recently?" or "what does the vendor say about this error?";
- when the runbooks are silent, the operator gets nothing but the escalation.

## 2. Why the current architecture is insufficient

- §1.4 rule 7 ("No diagnosis is claimed for an incident that matches no registered class") is right, but today it also
  means **no structured investigation** of such incidents beyond the evidence pack.
- §15.1 verifies only after an Argus action; ACR-0020's manual repairs and ACR-0019's actions both need a follow-up
  check recorded on the incident.
- §12.2 has no read for recent changes (image digests, container recreation, configuration differences), the most
  useful question in an incident (RB-018).
- §15.3 recall covers runbooks only; vendor documentation is reachable only through the model's memory.

## 3. Smallest reasonable change

### 3.1 Open investigation (OD-15 → decided, §1.3)

For an incident with no matching class that a human or an alert reported, Argus runs a bounded **open investigation**
instead of only the evidence pack:
- Level 1–2 reads on the reported target and its declared dependencies, under a budget (`ARGUS_OPEN_MAX_STEPS`, reads
  per step);
- its result is **findings and suggestions** (`suggest_action`), never a diagnosis and never a proposal;
- the outcome stays `unsupported_escalated`, with the findings attached;
- it is off by default and enabled per scope (`config/policy.yaml` `open_investigation.scopes: [lab]`);
- rule 7 is unchanged: "no diagnosis is claimed".

### 3.2 Follow-up checks (§15.1)

Argus starts a linked check investigation (`parent_id`) on the same target automatically:
- after an approved action's `verify` (ACR-0019), when the prediction window ends;
- after an operator terminal session linked to an incident closes (ACR-0020), or when the operator clicks "I did it
  manually";
- after an alert resolves while its incident is open.

The result is recorded as the incident's verification (`recovered_verified`, `still_failing`) and in the memory of
actions with its origin (`argus_action`, `manual`, `self_resolved`).

### 3.3 New reads (§12.2)

| Read | Returns | Level |
|---|---|---|
| `changes.recent(target, window)` | Docker events, image digest changes, configuration-copy differences, and the deploy events (`deploy_event`, T-0045) | 2 |
| `config.read(host, path)` | an allowlisted file, redacted, with its SHA-256; periodic copies for history | 3 |
| `knowledge.reference(query)` | passages of the curated vendor corpus (§3.4), with id, URL and version | 3 (in-worker) |
| `knowledge.tool_doc(capability)` | the action card and its documentation | 3 (in-worker) |
| `metrics.compare_baseline` (extended) | the same value at the same hour over the last 7 days ("4× normal") | 3 |
| `knowledge.prior_incidents` (extended) | also the action, its basis and its verified result (ACR-0019 §3.12) | 3 |

Each read follows §12: a `CapabilitySpec`, the inspection policy, redaction, `InvokeCapability`, evidence, audit.

### 3.4 Curated reference corpus (§15.3)

- `argus/reference/`: passages of official documentation (Docker, Podman, Redis, PostgreSQL, nginx, systemd).
- Each passage carries `id`, `source_url`, `product`, `version`, `retrieved`, `authority` (`vendor` | `community`) and
  `licence`, and is reviewed in a PR like a runbook.
- Searched in the worker like the runbooks, and stored as evidence with its hash.
- It can be a **ground** for a proposal (basis `reference`, ACR-0019 §3.5), together with the service card.

### 3.5 Research from the internet, isolated, suggestions only

- **Off by default.** `config/research.yaml` enables it per class or scope, and only when the code finds no
  catalogue action or no internal source (the model returned `suggest_action`, or the incident escalates "no tool / no
  source"). It runs **after** `record`, in the background, never inside the decision loop.
- **A separate container `argus-v18-research`:**
  - its own queue only; no access to Argus's database, ledger or policy; no gateway tokens; no tools;
  - outbound only through a proxy with a domain allowlist (the search API and documentation domains, reviewed in a PR).
- **The query is built by code,** from the error signature redacted by the `Redactor`: no host names, addresses,
  internal names or secrets. The model never writes the query.
- **A quarantined reader model** (no tools) turns pages into a fixed schema: a summary, steps, exact quotes with URLs.
- **The deciding model never sees it.** The result goes only to the operator's suggestion card, marked "External
  source, unverified". It never enters the incident context or the grounds (a ground pointing at a research result is
  `InvalidDecision(malformed)`, ACR-0019).
- **The operator's choices on the card:**
  - "Convert to proposal" (only if a step maps to a catalogue action the service card permits; basis `operator`;
    human approval);
  - "I did it manually" (a follow-up check, §3.2);
  - "Propose to corpus" (a draft passage for a PR);
  - "Dismiss" (with a reason).
- **Stored:** `research_request` (the redacted query) and `research_result` (URL, domain, quote, summary, reader
  model, time), linked to the incident.

**Alternatives considered:**
- A: **keep the evidence pack only** for unclassified incidents: safe, but operators get nothing to act on.
- B: **let the deciding model browse:** rejected (prompt injection, exfiltration through queries, unbounded cost).
- C: **only the curated corpus, no live research:** acceptable as the first step. Research stays off until the corpus
  proves insufficient.

## 4. Consequences

- **Code:**
  - the open-investigation strategy (reads + `suggest_action` only);
  - follow-up triggers in the worker;
  - the new reads (§3.3) and their probes or executors;
  - the reference corpus loader;
  - the research container, proxy, reader and its tables;
  - the suggestion card in the UI.
- **Tests:**
  - an open investigation never proposes, never concludes a class, and respects its budget;
  - follow-up checks are linked and recorded;
  - each new read follows its inspection policy and redaction;
  - research:
    - its queries contain no host, address, internal name or secret;
    - it cannot reach a non-allowlisted domain or Argus's database;
    - its results never appear in a model request or a ground;
    - injection fixtures in fetched pages change nothing;
  - the evaluation uses recorded fixtures (no network in CI).
- **Brain:**
  - `policies/NETWORK.md`: the research proxy and its domains;
  - `policies/SECURITY.md`: the search API key, only in the research container;
  - `infrastructure/environment.md`: the research container.
- **Risk:** prompt injection through pages (mitigated by the quarantined reader, the operator-only output and the
  data tags); outbound data (code-built, redacted queries); cost (per-incident and daily caps).
- **How to reverse it:**
  - `open_investigation.scopes: []`;
  - `research.enabled: false` and stop the container;
  - the reads and the corpus are additive.
- **Safety principles touched:** secrets (outbound) and evidence integrity (new evidence kinds). Second approval
  required. Rule 7 is kept.

## 5. Decision

Proposed by juanbetancurm and conantkd. The open investigation, follow-up checks, new reads and the curated corpus
can start after ACR-0018; live research comes last and starts disabled.

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§1.3, §12.2, §15.1, §15.3, §25 OD-15, changelog), version bumped
- [ ] `policies/NETWORK.md`, `policies/SECURITY.md`, `infrastructure/environment.md`
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
