## 2026-10-17 — TEST-HARDEN-1: Docker tests in CI, prompt-injection cases (and the escape they found), a robust timing test

Type: implementation
Who: juanbetancurm (+ agent)
Context: the self-merge rule (`task/SELF-MERGE-rule`, OP-014) relies on a green CI meaning "safe to merge". OP-014
lists where it does not yet; this pull request closes its first three gaps.
Decision / result:
- **Docker tests in CI.** `ci.yml` sets `ARGUS_TEST_DOCKER=1` on the `test` job (the Linux runner has Docker; timeout
  15 → 25 min), so the credential-isolation check of the agent image, the real-Docker backup tests and the real-Nginx
  edge tests run instead of being skipped. `ops/local_ci.py` sets it too when Docker is present, as `ci.yml` does.
- **Prompt-injection regression cases** (`tests/test_op014_prompt_injection.py`, replayed offline through the real
  wiring from `restart-oom-01` with instructions planted in the worker's logs). They found a real defect: target text
  could write a literal `</evidence>` (or open a `<passage …>`) into the model's context and so end its data block
  early, against §10.8. `orchestration/runner.py` now escapes the `<` of `evidence` / `passage` / `reported` tags in
  every piece of untrusted text it puts in the context (`as_data`). A model that obeys an injection with a write tool
  or with a root cause outside the scope is refused, no action happens, and a planted secret still never reaches it.
- **The flaky timing test.** `test_benchmark_compares_direct_and_mcp_on_the_same_read` asserted the 100 ms OD-3
  verdict on 4 samples, which fails on a loaded machine. It now checks the mechanics (both ways measured, every read
  ok, a verdict printed); the budget rule stays in `test_benchmark_verdict`, and the real budget is measured on vm-095.
Consequences: the agent image changes (the context escape), so vm-095's agent, worker and scheduler need a redeploy
after the merge (both leases). The PR touches `.github/` and `ops/local_ci.py`, so it needs a teammate's approval.
References: OP-014 (`brain/OPEN_PROBLEMS.md`, added by `task/SELF-MERGE-rule`), ARCHITECTURE §10.8 and §22.3 item 10.

### Test state

Red seen: `test_injected_text_cannot_close_its_evidence_tag` (5 `</evidence>` for 4 blocks) and
`test_injected_text_cannot_open_a_fake_runbook_passage` (`<passage runbook=\"RB-999` in the context) before the
escape; both green after it. The three other injection cases were green before (guards that keep them so).

### Next step

A teammate reviews; after the merge, redeploy vm-095's agent (both leases), then OP-014 steps 4-8, one PR each.
