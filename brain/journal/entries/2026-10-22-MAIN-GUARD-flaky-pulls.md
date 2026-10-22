## 2026-10-22 - MAIN-GUARD-flaky-pulls: verify-main waits out GitHub's own 5xx answers

Type: implementation
Who: juanbetancurm (+ agent)
Context: main-guard on main has been red since #277 (runs on #277, #279, #273, #276, #275 and a re-run of #275).
Each time verify-main stops with `gh api repos/{owner}/{repo}/commits/<sha>/pulls: unexpected end of JSON input`,
on a different commit each run. Reproduced locally: that endpoint sometimes answers HTTP 500 with an empty body, and
a later call answers 200. verify-main asks about every first-parent commit on main (about 273), and `gh_json` gave
each call 3 tries, 2 s then 4 s apart, so one bad window of a few seconds turned main red. `brain.py start` hit the
same error today (it printed the WARNING and still claimed the lease). Not a fault in the code under review.
Decision / result:
- `brain/tools/brain.py` `gh_json`: a GitHub server error (`HTTP 5xx`), gh's `unexpected end of JSON input`, an
  empty error, or an answer that is not JSON is tried `GH_TRIES_5XX` = 6 times, 2, 4, 8, 16 and 30 s apart (about a
  minute), then raised as before. Any other failure keeps 3 tries, 2 s then 4 s apart; a 404 is still raised at once.
- Real failures still fail: a commit with no pull request, a missing approval and a 404 are unchanged; GitHub
  answering 5xx for over a minute still raises, so main-guard goes red then. Worst case added per bad call: about
  60 s, inside the job's 15 min (the run takes 3.5-4.5 min).
- Not chosen: skipping commits an earlier green run already verified. It would need state between runs (a file or a
  cache in CI) and makes a green run depend on an earlier one; the longer wait is enough for what was seen.
- No change to `.github/`. `brain/tools/brain.py` and `tests/brain/` are protected: conantkd reviews.
Consequences: main-guard should go green on the next push to main if GitHub's 500 window is shorter than a minute.
If it stays red with the same error, the window is longer and the next step is the skip-verified design.
References: #277, #279, #275, [GIT_WORKFLOW](../../policies/GIT_WORKFLOW.md).

### Test state

- **RED seen:** with only the `GH_TRIES_5XX` name added, the new tests failed on behaviour: the 5xx, empty and
  `unexpected end of JSON input` cases raised after 3 tries, and the "keeps answering 5xx" and "never JSON" cases
  made 3 calls instead of 6 (**6 failed**).
- GREEN: `-k "gh_json or verify_main or check_main"`, **15 passed**. The old "gives up" test now uses an HTTP 403
  (not a server error) and checks it keeps 3 tries and the 2 s, 4 s waits.
- Full offline suite on `6a72339` plus this change: **1638 passed, 62 skipped, 1 deselected**, exit 0 (the known
  detached-CI Brain test). Brain lint clean, `git diff --check` clean.

### Next step

conantkd reviews the PR (protected paths). After it merges, the next main-guard run on main shows whether the
minute is enough.
