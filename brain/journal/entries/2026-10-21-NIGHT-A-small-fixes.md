## 2026-10-21 — T-0046 L1 follow-ups; `host.read_file` raised on every successful read

Type: implementation
Who: conantkd (+ agent)
Context: conantkd's review of #219 (T-0046 L1) left two non-blocking notes.
Decision / result:
- The inventory loader refuses a `depends_on` that names the same dependency twice (as a plain ref or with another
  port): `TargetInfo.link()` would keep the first one silently and the map would draw two edges on one port. Red seen
  on the old loader (`tests/test_t0046_l1_links.py`, two new cases).
- `trace_request_path`'s docstring: a dependency on another host is refused by the inventory (ACR-0025); the branch
  that lists one stays as a guard (`test_t0040` feeds one directly).
- **Found while writing ACR-0028's canary test:** `host_read_file` passed `truncated=` to `CapabilityResult`, which
  has no such field, so every successful `host.read_file` raised `TypeError`. The gateway's tests never ran the Argus
  side. It is offered to no class today, so it never fired on the VMs. Now "more lines before" is `partial` with a
  `coverage`, and `tests/test_t0019_batch3b_host_verbs.py` runs the capability (red seen).
Consequences: none for today's inventory (no repeated dependency; it still loads and renders the same).
References: #219, ACR-0025.
