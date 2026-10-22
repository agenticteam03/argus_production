# Review report and helper evidence

Save the review as an English text file in the team's current approved text
location. Keep the PR number, reviewed head and fetched main SHA explicit.

```text
Goal and scope: <task, behavior and changed files>
Reviewed head: <sha>; fetched main: <sha>
Since approval: <first-parent changes, every merge and its resolution>
Validation: <local full suite, RED evidence, required CI on this head, Brain checks>
Discussion: <all reviews and comments read; remaining concerns and their resolution>
Findings: <severity, file/line, trigger, consequence and requested correction>
Recommendation: <ready for developer decision, request changes, or evidence missing>
If not ready: <each failing check: code/infrastructure/unknown, evidence, next check>
After merge: retain the task branch; run the policy's main verification.
```

Use `since_approval.py` even when a merge is titled "Update branch"; its automatic
merge comparison comes from Brain. A nonempty remerge diff needs examination, and
a resolved conflict always needs another approval under REVIEW_PROTOCOL.

`merge_ready.py --pr <number>` makes GET requests only and paginates files, reviews,
conversation/inline comments and check runs. It compares remote main to local
`origin/main` and refuses changed/incomplete evidence. The preview prints all
discussion text and a digest covering the head and those complete records. Read
them, assess their concerns, then pass that digest with `--discussions-read`.
`--findings-clear` attests that the reviewer assessed and cleared findings;
`--keep-branch` records the required branch-retention commitment. Neither flag is
an approval. A later comment or review changes the digest.

For a failing run, optional `--check-diagnoses <file>` reads a JSON object keyed by
check-run id. The value has `category` (`code`, `infrastructure`, or `unknown`) and
`evidence` (a log reference or observed detail). Without evidence it stays unknown.
An infrastructure diagnosis does not make a failing run pass. A newer successful
run must be completed on the exact head. When required CI did not run at all, the
existing Brain rule judges a non-author's exact-head `LOCAL CI PASS` comment.
Without a valid teammate approval, the helper also delegates full self-merge
eligibility to Brain; the policy's size limit still applies to unprotected paths.

For offline replay/tests, `--snapshot <file>` replaces live GitHub reads. Its object
must contain `complete: true`, REST-shaped `pr`, `main_sha`, `branch_exists`, and
complete lists `files`, `checks`, `main_checks`, `reviews`, `comments`, and
`review_comments`. Check runs include `id`, `name`, `head_sha`, `status`, and
`conclusion`; renamed files also include `previous_filename`. A recorded verdict
applies to those captured SHAs, not a later remote state.

`rollup_check.py` reads removed entries at the base, then calls the fetched Brain's
`split_entry` and `rebase_links`. Section markers move by that official format;
the journal and each section's full rebased payload must survive as a contiguous
block in the designated summary. Entry chronology follows Brain's roll-up command.
The helper never edits or removes an entry.
