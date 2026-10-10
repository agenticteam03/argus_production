# Sessions

The **live** session lease is not stored here: it is `session.json` on the dedicated `session` branch, managed only by
`python brain/tools/brain.py` (`status`, `start`, `renew`, `handoff`, `release`).

```json
{"holder": "<github-handle>", "session_id": "...", "task": "T-0013", "branch": "task/T-0013-langgraph-skeleton",
 "base_commit": "<sha>", "started_at": "...", "expires_at": "...", "released": false, "handoff": null,
 "vms": {"vm-095": {"holder": "...", "expires_at": "...", "released": false, "...": "..."},
         "vm-166": {"holder": "...", "expires_at": "...", "released": false, "...": "..."}}}
```

- **One lease per VM** (LANES-1, [`../policies/PARALLEL_LANES.md`](../policies/PARALLEL_LANES.md)): `vms` holds them;
  `brain.py start --vm vm-095|vm-166|both` (default both). A claim is all or nothing.
- The top-level fields are a **summary** for a `brain.py` older than LANES-1 (a branch made before it): busy while any
  VM is held, holder `a+b` when two developers hold one VM each (an old `start` then refuses everyone). A renew or
  release that an old `brain.py` writes to the summary is applied to its holder's leases. A `session.json` without
  `vms` (the old format) holds both VMs.

- TTL 60 minutes, renewed at every step boundary; `renew --minutes 120` before a long operation.
- A claim succeeds only if there is no lease, it is released, or it has expired; two simultaneous claims → Git
  accepts exactly one (fast-forward push).
- Taking over an expired lease records `took_over_from` in the journal and starts with the state probe; the previous
  holder's branch is never modified without talking to them.
- On each VM, `/opt/argus-v18/SESSION` mirrors that VM's holder; mutating `code.bash` blocks refuse if it is not you.

Session history = the commits of the `session` branch: `git log --format='%ci %s' origin/session` (claim, renew,
handoff, release — who and when).
