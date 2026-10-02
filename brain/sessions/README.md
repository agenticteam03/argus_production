# Sessions

The **live** session lease is not stored here: it is `session.json` on the dedicated `session` branch, managed only by
`python brain/tools/brain.py` (`status`, `start`, `renew`, `handoff`, `release`).

```json
{"holder": "<github-handle>", "session_id": "...", "task": "T-0013", "branch": "task/T-0013-langgraph-skeleton",
 "base_commit": "<sha>", "started_at": "...", "expires_at": "...", "released": false, "handoff": null}
```

- TTL 60 minutes, renewed at every step boundary; `renew --minutes 120` before a long operation.
- A claim succeeds only if there is no lease, it is released, or it has expired; two simultaneous claims → Git
  accepts exactly one (fast-forward push).
- Taking over an expired lease records `took_over_from` in the journal and starts with the state probe; the previous
  holder's branch is never modified without talking to them.
- On the VMs, `/opt/argus-v18/SESSION` mirrors the holder; mutating `code.bash` blocks refuse if it is not you.

Session history = the commits of the `session` branch: `git log --format='%ci %s' origin/session` (claim, renew,
handoff, release — who and when).
