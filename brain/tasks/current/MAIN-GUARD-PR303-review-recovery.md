# MAIN-GUARD-PR303 - Recover the missing final review of PR #303

| Field | Value |
|---|---|
| Status | `in progress` - recovery of #303 prepared; a teammate's review is required before merge |
| Owner | `conantkd` (+ Codex); review by another team member |
| Branch | `task/main-guard-pr303-review` |
| Needs the VM lease | no; repository review evidence only |

PR #303 merged as `d41b9ea2244dcf97e38f4365d9e0ca74b88d8406`, with final head
`d76f7427cb808649094013a93013df68af677311`. The last recorded teammate approval covers
`7b6902a8357dd7039da01360ae8c250d9ae5d825`. It does not cover the subsequent manual protected-path resolution.

## Review required

- Inspect `b8533b8a73c96d5b2b7927ffa2ce0ac5fd5c4268` with `git show --remerge-diff`: the architecture version history,
  audit-integrity description and credential table, ACR-0018's retention wording and completed-secret note, and the
  task/journal edits. Its nonempty remerge diff invalidates the earlier approval.
- Inspect `d76f7427cb808649094013a93013df68af677311`; its remerge diff is empty.
- Review PR #303's final content, including protected architecture and security paths, and the single retrospective
  record proposed here. Earlier review notes assigned to steps 5b/5c remain assigned there; this recovery does not
  turn on the digest job or authorize a deployment.
- Approve this recovery PR only if that review accepts the final #303 content. The author cannot supply that
  approval. A draft, an exception in an unmerged branch or a helper pass does not establish acceptance.

## Integration order

1. Obtain the teammate's approval of this recovery PR, wait for its required checks and merge with a merge commit.
2. Preserve the branch and require `main-guard` to pass on the resulting main commit.
3. Update PR #300 from that main, require its checks, replace its active changes-requested review with a new
   developer approval and merge with a merge commit. Preserve #300's source branch.

References: [review protocol](../../agents/REVIEW_PROTOCOL.md),
[PR #303](https://github.com/agenticteam03/argus_production/pull/303),
[failed main-guard](https://github.com/agenticteam03/argus_production/actions/runs/40115433517/job/120935621714),
[journal](../../journal/logbook.md).
