# Policy — security and secrets

## Secrets: where they live, and nowhere else

| Secret | Where it lives | Never in |
|---|---|---|
| SSH key to the VMs | each developer's laptop, `~/.ssh/` | Git, the Brain, chats |
| Executor tokens (gateways, probes) | `/opt/argus-v18/secrets/` on the VMs (0700 root) | Git, `code.bash`, `output.bash` |
| Tunnel key | `/opt/argus-v18/secrets/tunnel/` on vm-095 | anywhere else |
| JWT signing key, Postgres passwords | `/opt/argus-v18/secrets/agent/`, `/opt/argus-v18/secrets/postgres/` on vm-095 | anywhere else |
| OpenAI API key | `/opt/argus-v18/secrets/agent/openai_api_key` on vm-095 | anywhere else |
| Each developer's Argus password (one account per person, no shared login: ARCHITECTURE §17.3) | their password manager; stored only as an argon2 hash in Postgres | anywhere written; never shared with another person |
| Deploy keys (read-only, one per VM) | `/opt/argus-v18/secrets/deploy/` on each VM | anywhere else |
| VM addresses | `~/.ssh/config` on laptops; `/opt/argus-v18/hosts.env` on the VMs | Git, the Brain |
| The UI's TLS key and Let's Encrypt account (ACR-0011) | `/opt/argus-v18/secrets/tls/` on vm-095 (`privkey.pem` 0400, readable by the edge's uid 101 only; `letsencrypt/` 0700 root) | anywhere else |
| The UI's public domain (ACR-0011) | `/opt/argus-v18/app/deploy/ui/vm-095.env` on vm-095 (gitignored) | Git, the Brain |

## Rules

1. **Never ask for, paste, print or commit a secret.** Use hidden prompts: `read -rsp "Password: " VAR; echo`.
2. **Never `cat` a secret file**, never `docker inspect` an Env section, never `env` inside an Argus container.
3. Before every commit, pre-commit runs the Brain audit (`brain.py audit --staged`); CI runs it again on every push,
   plus gitleaks over the full history. A planted fake secret is blocked (tested).
4. **Forbidden in the repository:** public IP addresses, private VM addresses, the names or details of personal
   servers, Windows user-profile paths, personal names (use GitHub handles), `-----BEGIN … PRIVATE KEY-----`, API keys.
5. **If a secret may have been exposed:** stop (it is a stop condition), tell the team, **rotate it** (generate a new
   one on the VM and redeploy), then record what happened in the journal **without** the secret.
6. Raw outputs (`output*.bash`) are gitignored; only a sanitized `evidence.md` per step is committed.

## Safety principles (changing any of them needs an ACR with a second approval)

The second approval may come from any team member, the author included, and one person may give both approvals
([AGENT_PROTOCOL §4](../agents/AGENT_PROTOCOL.md)).

- **Read-only:** no write capability is released; the write gate in `config/policy.yaml` stays empty.
- **Host isolation:** an executor is resolved for the target's own host only, never another host.
- **Evidence integrity:** evidence and audit are insert-only; the runtime database role cannot UPDATE or DELETE them.
- **Least privilege:** gateways expose exact GET routes; probes expose typed verbs; tokens per service. The only
  public listener is the UI edge (ACR-0011): the UI contract's routes only, read or investigate tokens only (an
  investigate token may start an investigation under quotas, ACR-0012, and nothing else), one account per person.
- **Secrets** as above.

## Everyone has sudo — the rails

- Never touch the protected objects (see [`../infrastructure/environment.md`](../infrastructure/environment.md)).
- `nonint-check.sh before/after` around every mutating step; any difference means **stop**.
- Every mutating block has a rollback line and is safe to re-run.
- Never reboot a VM: they are shared; a reboot is a team decision.
