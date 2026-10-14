# T-0016 step 4e — evidence: the read-only UI on vm-095's public address (2026-10-14, conantkd)

Both leases (session 35297684bd04). Run by conantkd's agent over ssh. The public address is kept out of Git
(`policies/SECURITY.md` rule 4): written `<PUBLIC_ADDR>` here, set only in `deploy/ui/vm-095.env` on vm-095.
Commands: [`code.bash`](code.bash).

**Decisions behind this step (`conantkd`, 2026-10-14):**
- **One approval.** ACR-0011 is deployed with one approval of two (`juanes6554`). The team assumed it; the second
  approval came 29 minutes later (`juanbetancurm` approved and merged #144, 04:35 UTC).
- **The certificate.** Let's Encrypt for the IP address (no domain): the `shortlived` profile, about 6 days, renewed
  automatically.
- **Shared accounts.** The three shared `operator` accounts stay for now: an accepted risk.
- **The network.** The OCI rule for 443/80 was opened by the team. Before it, from the Internet, 80 and 443 timed
  out while 22 answered.

## Before

- From a laptop, `<PUBLIC_ADDR>`:443 and :80 timed out.
- A `tcpdump` on vm-095 showed the SYN to :443 arriving on `enp0s6`. OCI passed it, and the host's `INPUT` (only
  tcp/22 accepted) dropped it, since nothing listened.

## Deployment

| Block | Observed | Result |
|---|---|---|
| P.1 vm-095 | `SESSION OK`; `DEPLOY OK: 8ee48c4a118f (task/T-0016-playwright)`; `ARGUS_UI_DOMAIN` set on the VM only (the checkout clean: the file is gitignored); `UI FIREWALL APPLIED: 2 rules (argus-v18-ui)`; `UI CERT BOOTSTRAP` (self-signed placeholder); the loopback edge removed, the public edge started: `running health=healthy restarts=0 user=101 ro=true`, ports `0.0.0.0:80`, `0.0.0.0:443` only; `NO INTERFERENCE` | OK |
| P.2 vm-095 | certbot 5.8.0 staging dry run for the address, `shortlived`: `The dry run was successful`; `ui-cert.sh issue`: `UI CERT ISSUED <PUBLIC_ADDR>: 6 days left; issuer: C=US, O=Let's Encrypt, CN=YE2`; `nginx reloaded`; `argus-v18-certbot.timer` enabled (03:00 and 15:00 UTC); `ui-cert.sh renew`: `6 days left, no renewal (at 3)`; `fullchain.pem` and `privkey.pem` 0400, uid 101 | OK |
| vm-166 | unchanged: `ref=main`; `NO INTERFERENCE` | OK |

## From the Internet (a laptop, no tunnel)

| Request | Expected | Observed |
|---|---|---|
| `http://<PUBLIC_ADDR>/incidents` | 301 to HTTPS | `301`, `Location: https://<PUBLIC_ADDR>/incidents` |
| `https://<PUBLIC_ADDR>/`, certificate validated (no `-k`) | 200, a trusted chain | `200 verify=0` |
| headers | HSTS, CSP, no framing | `Strict-Transport-Security: max-age=31536000`, `Content-Security-Policy: default-src 'self'; …`, `X-Frame-Options: DENY` |
| `/docs`, `/openapi.json` | 404 | 404, 404 |
| `/api/v1/me` without a token | 401 | 401 |
| `/runbooks/index.json` without a token | 401 | 401 |
| `POST /api/v1/investigations` | 404 | 404 |
| a failed login of a made-up user | 401, audited with the **real** client address | `401`; `access.login_failed | edge | <the laptop's public address>` (the same address an outside service reports) |

**Reading:**
- **The real client address reaches the API on the public path.** Docker's DNAT keeps the source, so the
  per-address limit and the audit see the browser. Step 4d's `172.30.0.1` came only from the tunnel's 127.0.0.1
  (Docker's userland proxy). No host Docker change is needed.
- `DOCKER-USER` holds two rules tagged `argus-v18-ui` (per-address connection limit 50 on 443 and 80); no other rule
  was touched.

**State after this step:**
- **The read-only UI is public** at `https://<PUBLIC_ADDR>/`.
- vm-095 runs `task/T-0016-playwright` `8ee48c4` (the agent with 4a; `argus-v18-ui` public).
- vm-166 is unchanged on `main`.
- Back to `main` at #144's AFTER-MERGE.

**Rollback:**
1. `ui-firewall.sh remove`;
2. `docker compose -f compose.ui.yml -f compose.public.yml down`;
3. `systemctl disable --now argus-v18-certbot.timer`;
4. optionally `deploy.sh main`.

The SSH path keeps working throughout.

**Open:**
- a person logs in from a browser and opens an incident;
- one account per person (an accepted risk until then);
- ~~ACR-0011's second approval~~: given by `juanbetancurm` with #144.
- The AFTER-MERGE to `main` (#144 + #145, D-003): vm-095 still runs the branch at `8ee48c4`.
