# ACR-0029 — Confirmed incident feedback and interpretable case memory

This is the documentation-only proposal for [T-0048](../../tasks/current/T-0048-incident-feedback.md).
The task calls this NEXT-PHASE area G; that area was deferred out of the merged
[NEXT-PHASE plan](../../tasks/current/NEXT-PHASE-supervised-remediation.md), which links it as a separate track.
The task's explicit scope is the basis of this proposal. Nothing here accepts the design, applies it to
ARCHITECTURE, enables a route, changes ranking weights or releases a target write.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | `juanbetancurm` (+ agent) · 2026-10-22 |
| Accepted by | pending team decision |
| Second approval (safety principle only) | required for least privilege and integrity of retained feedback/audit; pending, per AGENT_PROTOCOL §4 |
| Architecture version | based on 1.8.28; next free version allocated only when accepted and applied |
| Task / PR | [T-0048](../../tasks/current/T-0048-incident-feedback.md); proposal PR pending |

## 1. Detect and explain

An incident ending in `diagnosed` says that Argus concluded, not that the conclusion was right. A closed incident
can currently become another investigation's precedent without an operator confirming its actual cause or fix:

- `IncidentMemoryPort.similar_incidents(target, incident_class, k)` returns earlier closed cases. The Postgres
  adapter filters by target, class and `closed_at`; it has no human-confirmation predicate.
- `knowledge.prior_incidents` (T-0039) returns the stored diagnosis, confidence, root-cause target and outcome.
  It cannot distinguish a reviewed correction from the model's original answer, or a failed fix from a verified one.
- ACR-0024 §3.3 explicitly defers weight calibration until confirmed outcomes exist. Its ranking is evidence-only;
  hypotheses, stored observations and `ranking_disagrees` already exist through T-0047 H1–H4.
- The UI API contract has no feedback route. Its read/investigate access cannot authorize this write
  ([API-FOR-UI](../../../docs/API-FOR-UI.md), rules 1, 2 and 6).

These are observed schema/interface gaps on main, not a measured claim about diagnostic quality. No quality gain
from feedback or similarity has been measured. ACR-0018 is accepted. On main `f480152`, WebAuthn and step-up are
implemented (PRs #280/#284); PR #288 is open and its deployment record on that branch documents migration 013,
the WebAuthn relying party and the audit chain on vm-095 at `77c4524` (49/49 database checks). The record says
operator enrollment remains pending. The private path (phase 16 step 4) and signed off-host audit digest/protection
(step 5) are not met on main or vm-095. The on-host audit chain is not evidence of off-host protection. All four
gates must be satisfied on the deployed profile before the feedback route is enabled; acceptance of this ACR remains
pending.

## 2. Why the current architecture is insufficient

The following quotations refer to [ARCHITECTURE 1.8.28](../ARCHITECTURE.md):

| Section and current text | Gap |
|---|---|
| §5.3: `diagnosed` means "diagnosis concluded; no action taken by Argus" | It is an execution outcome, not a ground-truth label. Rewriting it would erase what the run actually did. |
| §8.1: `similar_incidents(target, incident_class, k)` | No confirmation, correction history or fix eligibility is represented. |
| §10.5: "Each includes date, diagnosis and outcome." | A recalled diagnosis can reinforce an earlier mistake. |
| §15.3: "same target/class first; redacted summaries only" | No definition of a confirmed case or an interpretable similarity score. |
| §16.2: on audit and evidence, "no UPDATE or DELETE" | The new labels and checks need equally explicit insert-only protection. |
| §17.3: "a UI write action needs a new ACR" | Feedback is a new privileged write, even though it changes no monitored target. |
| §21.2: "≥ 5 trials per case per candidate model" | A memory prior needs a leakage-controlled comparison under the existing quality and hard gates. |

§7.1 has no feedback route; §6.1 has no feedback/verification use case; §§15–16 have no place to retain a human
correction independently of a machine conclusion. ACR-0018 supplies the access model, not this feature's contract.

## 3. Smallest reasonable change

All before → after text below is proposed for a later application PR. Existing incident, evidence, hypothesis and
audit records remain the record of the original run. The feature adds facts about that run instead of changing it.

### 3.1 Append-only feedback and verification (§5.7, §15.1–§15.3, §16.1–§16.3)

**Before:** episodic memory has incident summaries and execution outcomes only.
**After:** add two insert-only tables and a read-only projection:

| Object | Proposed minimum contents and rules |
|---|---|
| `incident_feedback` | Server-issued id, incident id, principal id, server time/order, expected predecessor (`supersedes_feedback_id`), idempotency key and canonical payload digest; verdict (`correct`, `partly_correct`, `incorrect`, `unknown`), actual class and root-cause target when known, cited evidence ids/hashes, fix kind (`none`, `manual`, `approved_action`, `unknown`), fix reference/time and bounded redacted summary. |
| `incident_verification` | Server-issued id/order, exact feedback id/digest, verifier/version, evidence ids/hashes and linked re-check id, observation window and source times; separate results for service recovery, cause resolution and stability (`verified`, `failed`, `unknown`), with reason codes. No human-supplied success flag is accepted. |
| `incident_outcome` | A SQL view over the active feedback and its qualifying verification records. Exposes label provenance, diagnosis verdict, confirmed cause, recovery/cause/stability results and `fix_usable`; never overwrites `Incident.outcome`, the original diagnosis, root-cause target or hypotheses. |

Feedback is corrected by a new row naming the active predecessor. There is one initial row per incident and at
most one successor of each feedback row; foreign keys/constraints and a per-incident transactional lock prevent
forks and cross-incident corrections. A stale predecessor returns 409, rather than silently replacing a newer
operator's label. Order is assigned server-side, not selected by a client timestamp. Every new head invalidates
the old head's eligibility; it does not inherit verification of a different payload.

Idempotency is scoped to principal + incident + key. Repeating the same canonical payload returns its original
result; reusing a key with a different payload is 409. An exact retry needs **no new step-up** and writes nothing:
no feedback, verification or additional audit event. Retry lookup still requires a live authorized human session,
permission, scope and private-path access. A consumed step-up can never authorize a new key or changed payload.

Actual targets must belong to the incident's host and allowed investigation scope; cited evidence must belong to
that incident or a directly linked, authorized re-check on that host, and its stored hash must match. Actual class
is a registered class or `other`, not arbitrary model text. `unknown` and a missing cause never manufacture a label.
The request cannot set actor, order, verification result, environment or evidence contents. Summaries are length
bounded (proposed maximum 500 characters), minimized and redacted before storage, audit, views and model context.

The deterministic verification use case consumes existing stored observations/snapshots and completed re-checks;
it does not run a model or issue a target read from the feedback HTTP handler. A new re-check still uses the existing
investigation path and its permissions/quotas. Automatic follow-up investigation is ACR-0022's separate track.
Verification runs after a feedback/re-check is durably recorded, with idempotent processing keyed by feedback,
evidence window/digest and verifier version; durable work delivery must be proved before this is deployed.

A qualifying recovery sample is newer than the fix's completion/reference time and within the configured freshness
bound. Stability needs the entire configured observation window and sufficient sample coverage; stale/missing data,
a gap or an unavailable verifier is `unknown`, never healthy. For an approved action the ledger supplies completion
time; a manual fix time remains an attributed human assertion. Late processing of an older window cannot displace
a newer failure. The view selects by observation-window end, then server order, not arrival time alone.

Service recovery and cause resolution remain distinct (§15.1). A healthy victim does not prove that its dependency's
cause was removed. Human confirmation of a cause requires the privileged label **and an observation from the original
incident** of that cause target (or a host observation explicitly naming it). Its known source time must be in the
incident's observation window and, when a fix is recorded, predate the fix. Linked re-checks may verify recovery,
cause resolution or stability; they cannot supply a missing observation of the past cause after it has been fixed.
If Argus never observed the actual cause, retain the human correction but leave `confirmed_cause` false/unknown;
it is ineligible for confirmed recall, the prior and export. A wrong original diagnosis can become a confirmed
*corrected* case only when the original run observed the actual cause but did not choose it. No later healthy
snapshot or human assertion alone retroactively proves the missing causal observation.

`confirmed_cause` means the current privileged human label has that valid supporting evidence. `fix_usable` further
requires a known fix, fresh verified recovery, verified cause resolution and a verified stability window for that
same feedback. A failed, regressed or unknown check prevents positive precedent for that fix. A later matching failure
removes eligibility immediately; older successful rows remain inspectable. No feedback is never confirmation.
This projection never promotes a manual fix to Argus's `recovered_verified` execution outcome.

The runtime roles receive minimum SELECT/INSERT, no UPDATE/DELETE on either table. Postgres grants and constraints,
SQLite insert-only triggers and adapter contracts prove this; retention uses the separate maintenance role. Feedback
and verification append plus their audit record must be atomic or fail closed. Audit records use ACR-0018's chain.
Corrections/retractions preserve the history; an attributed unknown/retraction head removes previous eligibility.

### 3.2 A human feedback route (§6.1, §6.7, §7.1, §17.1–§17.3)

**Before:** no use case or route for operator labels; read/investigate access permits no feedback write.
**After:** `RecordIncidentFeedback(incident_id, payload, authenticated_principal)` and
`RecordIncidentVerification(feedback_id, stored_evidence)` use cases, with this proposed HTTP route only:

| Route | Authorization | Response |
|---|---|---|
| `POST /api/v1/incidents/{id}/feedback` | human principal, live session, `feedback` permission and incident/target scope; privileged private path per ACR-0018 | 201 with feedback id, predecessor and confirmation pending/known; exact idempotent replay returns the original result |

Unchanged token narrowing applies: `read` and `investigate` tokens are refused even if the role lists `feedback`.
Service/peer/model principals cannot label causes or submit this route. The server derives actor from the principal;
scope failures hide the incident with 404 and are audited. Invalid/no session is 401, insufficient authority is 403,
invalid schema/evidence is 422 and a conflicting correction/idempotency key is 409.

Cause labels require a fresh, single-use step-up (≤ 5 min), bound to incident + predecessor + canonical label/fix
payload digest and the principal/session. Changed payloads, expired tokens, another incident or replay cannot write.
The conservative proposed first release requires step-up on **every** new feedback/correction, including retraction;
whether non-label notes may be exempted is an open acceptance decision (§5). No exemption is inferred from a role.

ACR-0018's accepted permission baseline includes `feedback` for the three enabled operators. This proposal grants
nobody anything: acceptance must confirm whether cause-label authority is narrower. `/me` advertises a feedback
action only when the built route, access, permission and private-path controls allow it. The public, unprivileged
edge answers 404; exposing this method through the privileged mTLS/address-allowlist path requires ACR acceptance
and the team's approval. Existing public logins remain read/investigate only; no new token scope is invented here.

The session/step-up transition and feedback append are race-safe. An audit failure leaves no acknowledged label;
an acknowledged label cannot exist without its audit. Do not put credentials, step-up tokens or unredacted payloads
in audit. Exact edge method/body/rate bounds and the UI contract are reviewed with the first implementation.

### 3.3 Confirmed memory and explicit similarity (§8.1, §10.5–§10.6, §10.8, §12.2, §15.3)

**Before:** `similar_incidents(target, incident_class, k)` / `knowledge.prior_incidents` recall closed cases without
confirmation metadata. **After:** add `confirmed_only` to both the port and capability arguments and pass it through
the internal executor and every adapter. Proposed default: `true`; the deterministic recall path and ranking always
request `true`. `false` is an explicit historical read, whose unconfirmed rows are labelled as such and are ineligible
for priors or positive fix precedent. Existing unlabelled rows are not backfilled as confirmed.

Filter confirmation **before** applying `k`; otherwise recent unconfirmed cases could hide an older confirmed case.
The bounded read keeps today's target/class restriction and `k ≤ 5`. Query by original detected incident class;
return the confirmed actual cause separately. Enforce current caller scope and host plus a server-derived environment
profile; lab/scenario feedback never supplies a production prior. No new cross-host search is authorized. Return
feedback/verification ids, label times, actual cause and distinct verification states, alongside the original verdict.
A failed fix may be returned as explicitly negative context, never as a successful fix or positive fix count.

`incident_features` is a versioned, deterministic projection of stored incident-time facts, not a mutable truth table
or an embedding index. Proposed features/weights: detected class (3), target kind (1), fired signal names (2), declared
dependency role (2), named failure-pattern set (2). Categorical equality or set Jaccard contributes its weight;
missing/unknown values contribute zero, even when both sides are missing. Divide by the fixed total weight (10).
Do not match free-text diagnoses, operator prose, future verification facts, secrets or model-generated labels.
Use only facts available before the current ranking step; include feature/inventory versions and an as-of cutoff.

Each result includes its matched features, weighted contributions, total similarity, source incident and active
feedback id. Similarity orders eligible cases, with incident time/id as deterministic tie-breakers; it is a match
score, never a probability. Unavailable memory produces no prior and preserves evidence-only behavior, not an error
that stops the investigation. Redaction/provenance and context bounds remain those of §§10.6 and 10.8.

### 3.4 A bounded prior for T-0047 (§11.3, §15.3; ACR-0024 §3.3)

**Before:** the support score counts only current evidence. **After:** retain that score and its counts unchanged,
and expose `evidence_score`, `case_prior`, source case/feedback ids and the resulting rank separately:

`case_prior(h) = prior_weight × Σ similarity(case) matching h's confirmed cause / Σ similarity(eligible case)`

An empty/zero denominator gives zero. Each incident counts once, regardless of correction/check count. A match uses
actual cause class and the in-scope cause target; prose matching does not count. Only a `supported` hypothesis with
valid evidence of its own target may receive a bonus. A prior cannot support an untested hypothesis, resurrect a
ruled-out one, satisfy §11.3, make an external cause choosable, change the conclusion or execute an action.

Proposed initial cap: `0 ≤ prior_weight ≤ 0.5`; **default 0** until the §3.5 comparison is reviewed. Positive fix
recommendations separately require `fix_usable`, never diagnosis confirmation alone. Feature weights, cap and any
later calibration are reviewed configuration under protected `config/ranking.yaml`, not model learning or a runtime
write. Persist the versions, as-of cutoff, source feedback ids and bonus with each new hypothesis ranking; old
rankings are immutable. `ranking_disagrees` still compares the chosen hypothesis to the displayed rank; the UI
distinguishes present evidence from past-case influence and never presents the combined score as confidence.

### 3.5 Offline export and evaluation (§21.1–§21.2, §15.3)

**Before:** evaluation cases are authored/reviewed in Git. **After:** an offline export produces a **draft** case
from a confirmed cause, never a committed fixture or an automatically changed label/runbook. The exporter reads a
sanitized snapshot with its active feedback/check ids, source hashes and version; immediately before export it
rechecks eligibility. A correction before review requires regeneration or rejection of the stale draft.

The draft maps stored facts to the existing case schema: target/request, bounded snapshots/tool fixtures, and labels
for actual class/root cause/expected hypotheses. It includes only replayable observations, no production credentials,
addresses, personal names or raw logs. Map real identities to reviewed synthetic inventory targets consistently;
if the necessary fresh observations/fixtures are absent, refuse export and name the missing inputs. Do not invent
a successful fix, a negative hypothesis or an executable action from operator prose. Provenance travels in the
PR's review material/journal, not as an unsupported extra YAML field (`extra="forbid"`).

Write to an explicit draft directory outside every evaluation loader/CI glob. A human inspects redaction, truth,
fixtures and labels; a PR review admits it to a chosen dataset. **An export never enters `tests/eval/heldout/`.**
OP-013's held-out discipline ([PR #266](https://github.com/agenticteam03/argus_production/pull/266)) requires cases
written without examining the strategy they measure; a real incident has already been through Argus's strategy
and recall. Exported cases belong to a separately declared regression/calibration set, not that independent set.
Export is neither permission to publish production data nor a new online route. No artifact is generated here.

The prior is evaluated on frozen cases with a memory snapshot predating each case. Exclude the case itself, its
re-checks/duplicate episode and exported descendants from its recall population; separate calibration/training
episodes from held-out evaluation episodes. Never populate memory with a held-out label before grading it. Compare
evidence-only and prior-enabled ranking on identical fixtures/strategies, at least five trials per case, reporting
mean/worst accuracy, top-1/top-3, disagreement, abstention, latency and cost. Existing §21.2 hard checks stay 0 and
quality cannot regress. Admission/calibration and a nonzero prior require reviewed results; no quality claim is
made by the unit tests or by this proposal.

### 3.6 Alternatives considered

- **Keep the architecture and put corrections in operator notes.** No enforceable confirmation filter, correction
  order or fix provenance; the next run can still repeat a wrong answer. Suitable only while the feature is gated.
- **Update the original diagnosis/outcome in place.** Loses the original run and makes historical evidence/rankings
  misleading. Rejected in favor of insert-only assertions and a projection.
- **Learn automatically from closed cases, model confidence or a successful command.** None proves the cause or
  durable recovery; reinforces mistakes and confuses recovery with cause resolution.
- **Embeddings or automatic weight training now.** Less interpretable and needs labels/split discipline not yet
  available. The deterministic projection and disabled-by-default bounded bonus are the smaller change.

## 4. Consequences

### 4.1 Affected implementation and tests (future application PRs)

The following is a test plan, not tests claimed to exist or to have passed:

| Change / sections | Implementation affected | Required tests and acceptance evidence |
|---|---|---|
| Feedback/verification/view, §§15–16 | domain models, port, Postgres/SQLite/fake stores, next-free migrations and `db-check` | runtime UPDATE/DELETE denied; SQLite triggers; correction fork/cross-incident/stale-head refusals; concurrent same-key idempotency; audit failure rolls back; only current-head checks contribute; delayed older checks cannot mask a newer failure |
| Human route, §§6–7/17 | inbound adapter, use case, ACR-0018 permission/step-up integration, `/me`, UI contract and privileged edge method | every route × role × principal kind × token access × scope × permission; revoked session; missing/expired/replayed/wrong-object/digest step-up; exact retry returns without a new step-up or any write, while a consumed step-up cannot authorize a new key/payload; actor spoofing; 404 on public path; no side effect on refusal; grant/revocation and durable audit |
| Verification, §15.1 | deterministic verifier and durable invocation after stored feedback/re-check | pre-fix/stale/gapped/missing recovery samples remain unknown; a healthy victim does not resolve its cause; cause evidence/target/hash/time validation; an unobserved corrected cause stays unconfirmed and a post-fix re-check cannot backfill it; fresh failure/recurrence removes positive fix eligibility; no model or target I/O in the HTTP handler; crash/retry loses no acknowledged work |
| Confirmed memory, §§8/10/12/15 | capability schema, internal executor, port and all adapters/recall callers | default true; unknown legacy rows excluded; filter before limit; retraction invalidates immediately; explicit false visibly unconfirmed; wrong-host/profile/scope/self episode excluded; failed fix never counted as success; redaction/injection fixtures on stored output and model input |
| Similarity/prior, §11.3/15; ACR-0024 | pure feature matcher, reviewed ranking config, ranking store/view | fixed/versioned feature contributions and ties; unknown does not match; bonus bounded and zero by default; one episode counted once; invalid/untested/ruled-out hypotheses gain nothing; evidence counts/decision unchanged; unavailable memory gives zero; historical ranks remain reproducible |
| Draft export/evaluation, §21 | offline exporter and review procedure | deterministic export; invalidated/no-confirmation cases refused; missing fixtures refused; sanitized synthetic targets; schema load; draft path excluded from loader globs; source/descendant leakage checks; paired ≥5-trial quality results and hard checks 0 before enablement |

### 4.2 Deployment, risks and reversal

- **Gate:** accept the ACR and its outstanding decisions first. The implementation that needs it applies the exact
  architecture changes/version/changelog with its first code; do not check that off in this proposal. Deploy only
  after the required ACR-0018 identity, permission, step-up, private-path and audit protections are built and proved.
- **Deployment:** next-free forward migrations before the API/worker image; minimum grants verified with real
  Postgres; no migration number reserved here. Start with feedback writes disabled and `prior_weight=0`; enable
  the route only after authorization/edge checks and team approval. No target-side executor or write-gate release.
  Any future deployment follows both VM leases, developer-run blocks and non-interference checks.
- **Risks:** an authorized but wrong label, two operators correcting concurrently, incomplete telemetry, a later
  recurrence, retained sensitive prose, profile mixing and evaluation contamination. Attribution/correction chains,
  evidence-bound separate checks, unknown states, redaction, scope/profile filters and frozen splits address them;
  they do not turn a human label into proof of universal causality.
- **Reverse writes:** disable the feedback route/action and pending feedback verification processing; keep read-only
  access to the historical rows. Revoke its grant if needed through ACR-0018's audited administration path.
- **Reverse memory/ranking:** set `prior_weight=0`, disable confirmed-case recall if its implementation is faulty
  and return to the existing evidence-only path. Do not silently fall back from confirmed-only to unconfirmed cases.
- **Reverse export:** stop the offline exporter; quarantine drafts. Cases already admitted need a reviewed follow-up
  PR. Keep the insert-only tables/audit; never delete labels or downgrade a migration to roll back behavior.
- **Safety principles:** **yes**, least privilege (a new human write) and evidence integrity (retained assertions,
  verification provenance and chained audit). Read-only target operation, closed write gate and host isolation stay
  in force; no new secret is needed beyond ACR-0018. The protected PR requires a teammate's approval and the second
  approval described in AGENT_PROTOCOL §4. Peer pre-review is not that GitHub approval.

## 5. Decision

**Pending.** Proposed defaults in §3 are reviewable choices, not grants or accepted policy. The team must decide:

1. **Who may label?** Confirm ACR-0018's `feedback` grant to the enabled operators, or restrict cause confirmation
   further; decide whether any second operator must review a disputed/production label. No new grant in this PR.
2. **Step-up for which labels?** Cause creation/correction/retraction always needs it. Proposed first release:
   every feedback write; decide whether non-label notes can be exempt without influencing recall or ranking.
3. **Confirmation and stability:** approve the evidence rules and separate cause/fix eligibility above; set the
   observation window, freshness/coverage limits and how a later recurrence invalidates a fix. Unknown stays unknown.
4. **Retention:** choose periods for feedback, checks and referenced evidence, and what happens when evidence is
   pruned. No confirmed eligibility may outlive the provenance needed to justify it; the maintenance role must not
   remove a referenced record first. Approve privacy/redaction and authorized export policy.
5. **Similarity and prior:** approve initial feature weights, same-target/profile restriction, cap and the evidence
   needed to set a nonzero weight. Confirm that no automatic weight update is authorized.
6. **Application slices:** decide when ACR-0018's deployment gates are met, the durable verifier delivery mechanism,
   and which offline dataset/split receives an exported case. No privileged edge change is approved by this draft.

Record the accepting developer, required approval and answers here in the acceptance PR. Rejected alternatives or
changes to these defaults remain visible in review; implementation waits for acceptance.

## 6. Applied

Not applied. This PR is the proposal only; its journal entry records drafting/validation, not application.

- [ ] ACR accepted and decisions/required approval recorded.
- [ ] `ARCHITECTURE.md` updated with the accepted text, next free version and changelog link.
- [ ] Application journal entry with implementation and deployment evidence.
- [ ] Architecture application and first code that needs it in the same reviewed PR, with this accepted ACR.
