# OP-013 step 03 — Peer label audit

## Scope and method

This is a supplemental audit for conantkd's pending label review of four OP-013 cases.
It does not make the OP-013 class re-decision and does not change labels or model JSONL.
The branch started from fetched origin/main df94464.

I recorded the provisional judgments below from the case fixtures, inventory, replay semantics,
and RB-003/RB-015 before opening OP-013's “Results so far” section (task line 50).
No model output was used to choose these verdicts.

“Observed” means written in a fixture, inventory, replay rule, or runbook. “Inference” is my
interpretation of those observations. The evaluator checks a present class field independently
of outcome; abstain forbids a diagnosed outcome (argus/evaluation/score.py:22-29). Thus
category: ambiguous cases can still carry an expected class while requiring escalation.

## Provisional fixture-and-runbook judgments

### heldout-nginx-wrong-upstream-port

**Intended mechanism:** nginx points to slow:8081 while the service listens on 8080
(OP-013 task:20-21,34).

**Observed:** nginx logs twice show connection refusal to slow:8081; the fixture's TCP
probe fails on 8081 and succeeds on 8080. The config has proxy_pass to slow:8081.
The upstream is running and logs a fast GET on 8080
(tests/eval/heldout/cases/heldout-nginx-wrong-upstream-port.yaml:25-28,41-55,
68-86).

**Current label/outcome:** diagnosed; class nginx_upstream_failure; root cause
vm-166/container:argus-lab-nginx; expected diagnosis includes 8081, port, or proxy_pass
(same fixture:95-104).

**Matching rule:** RB-015 says a wrong peer/port supports H2/H5 and an equivalent
backend success leads to proxy configuration investigation (argus/runbooks/
RB-015-nginx-upstream-failure.md:40,66-80). Inventory declares slow's TCP port 8080
(config/inventory.yaml:34-40).

**Inference and provisional verdict — supported:** the refusal on the configured port,
working 8080 listener, and explicit proxy_pass mismatch distinguish proxy configuration
from a down or slow backend. The nginx root-cause label is supported.

### heldout-nginx-header-too-big

**Intended mechanism:** nginx rejects a fast upstream response header larger than its
configured buffer (OP-013 task:20-21,35).

**Observed:** nginx logs say “upstream sent too big header”; slow logs a 0.1 s response
with a 9 KiB Set-Cookie header, while nginx config sets proxy_buffer_size to 4k.
Both containers are running without restarts
(tests/eval/heldout/cases/heldout-nginx-header-too-big.yaml:14-27,41-54,73-80).

**Current label/outcome:** diagnosed; class nginx_upstream_failure; root cause
vm-166/container:argus-lab-nginx; expected diagnosis includes header or buffer
(same fixture:88-96).

**Matching rule:** RB-015 includes header/protocol errors and H5 route/header/config
regression; its decision tree sends an equivalent backend success to proxy configuration
investigation (argus/runbooks/RB-015-nginx-upstream-failure.md:36,40,66-80).

**Inference and provisional verdict — supported, with ownership ambiguity:** the observed
failure is at nginx's 4k response-header buffer, not latency or backend availability.
The fixture does not state the accepted cookie/header contract or a known-good buffer.
The oversized value may also be an upstream behavior issue; conantkd should decide whether
the nginx root-cause attribution is sufficiently established.

### heldout-dep-backend-flap

**Intended mechanism:** one client timeout and network reconnect occurred, but the backend
answers now and the failing layer is not established (OP-013 task:20-21,30).

**Observed:** the client logs one timeout among 30 requests. Client and backend are running
on argus-lab-app; backend logs two 200s and has disconnect/connect events. DNS and TCP
probes now succeed, and the replayed wildcard network result is 200
(tests/eval/heldout/cases/heldout-dep-backend-flap.yaml:23-61,197-210).

**Current label/outcome:** no_action_escalated; class dependency_unavailable; abstain true
(same fixture:211-214).

**Matching rule:** RB-003 distinguishes dependency layers, says TCP success is not
application health, and calls for multiple hypotheses when the failing layer is unexplained.
A healthy nearby probe weakens a global outage but cannot exclude client-specific faults
(argus/runbooks/RB-003-dependency-unavailable.md:24,74-77,90-102).

**Inference and provisional verdict — supported for escalation:** the isolated timeout is
a real symptom, but current success plus the reconnect does not prove a persistent failure
or assign causality. Escalation without diagnosis fits RB-003 and the abstain label.

### heldout-nginx-errors-no-trace

**Intended mechanism:** gateway errors are reported, but proxy logs show no upstream error,
the upstream is fast, and the failing layer is not identified (OP-013 task:20-21,36).

**Observed:** the trigger reports a 502 and a 0.6 five-minute error ratio. However, nginx
logs two 200s, slow logs two fast responses, the config points to slow:8080, and the
network fixture wildcard returns status 200
(tests/eval/heldout/cases/heldout-nginx-errors-no-trace.yaml:6-11,25-27,41-55,
68-80). Replay chooses that wildcard when no keyed, exact, or derived answer exists
(argus/evaluation/replay.py:65-85).

**Current label/outcome:** no_action_escalated; class nginx_upstream_failure; abstain true
(same fixture:89-92).

**Matching rule:** RB-015 says a 502 alone does not locate its source; unknown error source
calls for bounded proxy metadata, and missing logs do not establish error-free service
(argus/runbooks/RB-015-nginx-upstream-failure.md:24,32,65-80).

**Inference and provisional verdict — uncertain:** abstention is defensible because no
upstream cause is shown. There is a fixture mismatch to resolve: the case description says
probes through the proxy failed (fixture line 1), while the replayed wildcard result is
HTTP status 200 (lines 68-73). The metric/reason report errors, but the fixture has no
explicit failing proxy probe. Please have conantkd decide whether this is a description,
fixture-response, or label-scope issue; I recommend no edit in this audit.

## Post-recording context

After saving the provisional judgments, I read OP-013 task:50-80. It says the labels were
not changed after the baseline run, both ambiguous cases escalated in every model_loop and
plan_then_reason trial, and the baseline diagnosed the ambiguous nginx case (task:58,70).
Those results did not change the judgments above. I did not open, edit, or regrade stored
model JSONL.

The fixture categories are class for the two diagnosed nginx cases and ambiguous for the
two abstention cases (each fixture:3). The expected class remains scored independently of
outcome, while abstain bars a diagnosed outcome (argus/evaluation/score.py:22-29).

Replay detail: the network.http_probe capability uses network_probe
(argus/capabilities/catalog.py:1111-1113). Replay derives only connectivity/log responses
for this executor (argus/evaluation/replay.py:94-95); with no exact route answer, this
case's wildcard status 200 is the replayed HTTP result.

## Validation (after paired review)

- Brain split_entry accepted the journal heading, fields, and both optional sections.
- Brain lint: lint: clean (exit 0).
- Brain audit: audit: clean (exit 0).
- TASK-17 peer review: PASS WITH NOTES; the unresolved label questions remain with conantkd.
- Ruff is not applicable to these Markdown-only changes.
- git diff --check: clean (exit 0, no output).
- All authored audit, journal, commit, and PR text lines are at most 120 characters.
- Full offline suite: 1,912 passed, 74 skipped, 1 deselected in 1929.72s (0:32:09); exit 0.
