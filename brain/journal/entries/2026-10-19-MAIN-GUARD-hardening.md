## 2026-10-19 — MAIN-GUARD hardening: `gh_json` retries; #183's open test case

Type: implementation
Who: conantkd (+ agent)
Context: main-guard once went red on `unexpected end of JSON input` (a cut-off `gh api` answer) and passed on a
rerun. The review of #183 left one case untested: a clean merge of a branch other than `main` after an approval.
Decision / result:
- **Retries:** `gh_json` tries a failed call or a non-JSON answer again, `GH_TRIES` = 3 in all, 2 s then 4 s apart. A
  real failure still raises `BrainError` after the last try.
- **404 is final:** a 404 is an answer, not a glitch (`verify-main` reads a deleted branch that way: not kept), so it
  raises at once with no wait.
- **#183's open case:** two tests pin that only a merge with `main` keeps an approval.
  - A clean merge of another branch needs a new approval.
  - The same code arriving through a branch that merged `main` first also needs one.
  - `only_main_merged_since` already refused both; the tests keep it so.
Consequences: no rule changes. `brain/tools/brain.py` and `tests/brain/` are protected, so a teammate approves.
References: `brain/agents/REVIEW_PROTOCOL.md` ("An update that only brings in main"), #183.

### Test state

- `tests/brain/test_brain.py` gains six tests.
  - **Retries:** a cut-off answer is retried; a failure is retried then raised after `GH_TRIES`; a good answer is
    read once; a 404 is raised at once. The first two were seen red first (no retry).
  - **Merges (#183):** another branch merged after the approval, and main reaching the branch through another branch.
    Both pass on `main` as it is: they guard existing behaviour.
- `tests/brain` green locally.

### Next step

A teammate's review and merge (protected paths: no self-merge).
