## 2026-10-12 — EVAL-5: the model sees which URL and port each target allows (EVAL-5)

Type: fix
Who: conantkd (+ agent)
Context: EVAL-3 step 2 and T-0019 batch 3c: `check_http_endpoint` was called 11 times on `argus-lab-slow`, which has
no HTTP endpoint in the inventory (TCP 8080 only); every call failed as `invalid_args`, and the three nginx misses
escalated or named no root cause after it ("the direct probe was invalid").
Decision / result: `InvestigationView.allowed_values` carries, per target in scope, the inventory's `http_endpoints`
(`url`) and `tcp_ports` (`port`), filled by both runners. In the tool definitions, a probe with such an argument is
offered only on targets with allowed values, the argument gets an enum, and the description lists them ("Allowed:
vm-166/container:argus-lab-nginx: http://argus-lab-nginx:8080/"). A probe with no allowed target is not offered.
Consequences: the model can no longer ask a URL or port the probe would refuse. Not yet measured with the model (both
leases were released; the next evaluation batch on vm-095 measures it, nginx cases first).
References: `argus/tooling/model_harness.py`, `argus/orchestration/runner.py`.

### Test state

`tests/test_tool_allowed_values.py`: 3 tests (red seen: no `allowed_values`, the probes offered on every target).

### Next step

Measure with the model in the next evaluation batch (nginx: 0.92–0.96 before).
