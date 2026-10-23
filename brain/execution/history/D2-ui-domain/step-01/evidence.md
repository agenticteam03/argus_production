# D2-ui-domain step 01 — evidence: the public UI moved from an address to a DNS name (2026-10-22 UTC, conantkd)

Goal: give the UI a DNS name so that WebAuthn has a relying party id (PHASE-16 step 3, D2 option (a)). The name is the
team's subdomain; it is kept in `deploy/ui/vm-095.env` as `ARGUS_UI_DOMAIN` and is not written here. Run by conantkd
(vm-095 lease `D2-ui-domain`); checked from the laptop by the agent. Sanitized: no name, address or key.

| Check | Observed | Result |
|---|---|---|
| DNS | an A record straight to vm-095, "DNS only" (a first try through the provider's proxy showed its edge certificate and two proxy addresses: switched off) | OK |
| Edge | `ARGUS_UI_DOMAIN` set to the name (a backup of the address version kept as `vm-095.env.bak-ip`); `resolves: this VM`; `argus-v18-ui` `Recreated`, `Started` | OK |
| Certificate | `UI CERT ISSUED <name>`: Let's Encrypt `YE2`, subject and SAN the name, 89 days left (the address certificate had 6) | OK |
| From the laptop | TLS verified (`ssl_verify_result=0`); `/healthz` 200; `http://<name>/` and `http://<address>/` 301 to `https://<name>/`; one address resolved, vm-095's | OK |
| After | `NO INTERFERENCE: non-Argus objects unchanged`; lease released | OK |

## Notes

1. **A first attempt wrote the agent's placeholder literally** (`<tu-subdominio>`, from commands given with a
   placeholder after the name was known): certbot refused the identifier, the live certificate stayed the address's,
   and the HTTP redirect pointed at the placeholder until the corrected run minutes later. HTTPS answered throughout.
2. **Renewal:** the existing `argus-v18-certbot` timer (twice a day, at 3 days left): with a 90-day certificate, once
   about every 3 months instead of twice a week.
3. **Rollback:** `sudo cp vm-095.env.bak-ip vm-095.env`, the compose `up` of the edge, then `ui-cert.sh issue` for the
   address.
