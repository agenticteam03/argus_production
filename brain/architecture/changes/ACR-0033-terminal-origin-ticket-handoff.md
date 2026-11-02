# ACR-0033 — Authenticate the isolated terminal frame before issuing its ticket

| Field | Value |
|---|---|
| Status | `proposed` in a separate draft; **do not review or approve yet** |
| Proposed by | conantkd (+ Codex) · 2026-10-25 |
| Accepted by | pending |
| Second approval (safety principle only) | pending; credential isolation and privileged access |
| Architecture version | pending after ACR-0020 and the private-login decision |
| Task / PR | [PHASE-21](../../tasks/current/PHASE-21-operator-terminal.md) · PR #327 |

## 1. Detect and explain

[ACR-0020](ACR-0020-operator-terminal.md) requires the launch ticket to be the WebSocket's first message, never a
URL value. It also puts the terminal document and byte channel on a dedicated origin and says that the parent SPA
never receives the ticket. The current §17.4 states both boundaries but does not say which document authenticates,
performs WebAuthn step-up and calls the ticket endpoint. No privileged ticket or WebSocket route exists in 21A, so
this is a design gap found before a browser implementation, not an observed deployment failure.

## 2. Why the current architecture is insufficient

The parent SPA's access token and browser storage belong to its own origin. The isolated frame cannot read them,
and letting the parent obtain and forward a ticket contradicts ACR-0020's "parent never receives the launch ticket"
boundary. A terminal-origin document calling the current API cross-origin would also need new CORS and WebAuthn
origin rules. §17.3 currently configures a single `ARGUS_WEBAUTHN_ORIGIN`. Implementation must not choose a
credential handoff or broaden the accepted WebAuthn origins silently.

## 3. Smallest reasonable change

Add this paragraph to §17.4 after the dedicated-origin frame boundary:

> The terminal frame authenticates as a human independently on its dedicated **private** origin. That origin
> proxies the private login and WebAuthn routes through the same mTLS and address-allowlisted edge; it stores its
> own full token in frame memory only. The frame performs its own object-bound step-up and calls the terminal
> ticket endpoint same-origin. It sends the ticket as the first message on a same-origin WebSocket, then erases it.
> The parent may pass only host, incident and reason as untrusted prefill through `postMessage`; both sides pin
> `targetOrigin`, and the frame checks the sender origin and window before using the prefill. The server validates
> all three fields. The parent receives lifecycle state only. Neither a token, ticket, keystroke nor output crosses
> the frame boundary. Reloading the frame requires a new login and ticket.

Add to §17.3's WebAuthn configuration:

> The terminal's dedicated private origin is an explicit second allowed WebAuthn origin for the **same fixed RP
> ID**, configured by exact origin rather than a wildcard. The server checks the ceremony's claimed origin against
> the origin of the authenticated request and the exact allowlist. The main UI and terminal keep separate browser
> sessions; a token from one origin is not imported into the other. A new origin is not enabled merely because it
> shares a parent DNS domain.

This depends on acceptance and implementation of [ACR-0032](https://github.com/agenticteam03/argus_production/pull/325)
or an equivalent accepted private full-token login. If that decision changes, this ACR must be revisited before 21C.

**Alternatives considered**

- Let the parent SPA call the ticket endpoint and send the ticket by `postMessage`. This puts the credential in the
  parent and weakens the isolation ACR-0020 requires.
- Put the ticket or a one-time bearer launch handle in the iframe URL. URLs leak through history, logs and referrers
  and violate ACR-0020's no-ticket-in-URL rule.
- Serve the terminal frame on the main UI origin with a sandbox and a separate CSP. This avoids a second login, but
  removes the origin boundary that protects terminal bytes and credentials from the parent SPA.
- Use a backend-mediated ticket handoff keyed by a public session ID. This needs a second browser-to-broker binding
  secret to stop anyone with the session ID from taking the ticket; it is a larger protocol than an isolated login.

## 4. Consequences

- Code and tests: exact terminal-origin edge route; an exact WebAuthn origin allowlist; a same-origin private login,
  step-up and ticket flow within the frame; strict `postMessage` validation and reload/revocation tests.
- Deployment: a dedicated private origin with the existing mTLS/allowlist controls and a fixed RP ID covering both
  allowed origins. No public route for login, ticket or WebSocket.
- Risk: a second authenticated browser context holds a full token. Frame memory, exact origins, short sessions and
  object-bound step-up limit exposure; no cross-origin token transfer is permitted.
- How to reverse: close the terminal origin and remove it from the WebAuthn allowlist; existing main UI access and
  the offline 21A broker core remain.
- Safety principle: **yes** — least privilege and credential isolation. Acceptance and a safety approval are needed
  before the browser and privileged API implementation.

## 5. Decision

Pending. This proposed ACR does not authorize a new origin, token flow, terminal route or SSH connection.

## 6. Applied

- [ ] ACR accepted with the required safety approval
- [ ] `ARCHITECTURE.md` updated and version bumped with the implementing code
- [ ] Private terminal-origin login, exact WebAuthn origin checks and frame tests implemented
- [ ] Deployment and network/recording evidence recorded in the phase task and journal
