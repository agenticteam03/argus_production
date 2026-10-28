## 2026-10-28 - X-8: release PR 3, network.restore on the lab API

Type: release (write gate)
Who: codexAgent2 (builder, lane S2b)
Context: Scenario 2 moves `argus-lab-api` from its declared `argus-lab-app` network to `argus-lab-iso`. The release pins one exact repair pair and uses `argus-lab-client` as the declared dependent for link verification.
Decision / result:
- `config/policy.yaml` opens the third reviewed pair: `network.restore` on `vm-166/container:argus-lab-api`.
- `deploy/action_gateway/first-lab-release.candidate.json` pins `POST /containers/argus-lab-api/network-restore`, connect `argus-lab-app`, disconnect `argus-lab-iso`. The gateway loader validates the entry and constructs the exact route map used by `ActionGateway`; no gateway service code changed.
- `config/inventory.yaml` allows `network.restore` for the API, declares its TCP port 8080, and makes `argus-lab-client` dependent on it. The generated `deploy/target/config/vm-166.json` now probes that client-to-API link. The API's service risk remains amber; the card is non-reversible.
- The policy engine accepts the network pair only on a `vm-166/container:argus-lab-*` target, and the standing tests require exactly the three reviewed pairs.
- ACR-0035 is marked accepted with architecture 1.8.44 / X-8. Conan's approval is the second safety approval; the developer and Conan approvals are required before merge.

Consequences: the release is an offline candidate only. No VM was used, no deployment occurred, and the release remains subject to both approvals.

### Test state

Focused release, write-gate, policy-pair, network-card, action-services, end-to-end and gate-report reference tests: 222 passed, 2 skipped. Ruff passed; `bash -n ops/write-gate-check.sh` passed using Git Bash. The full suite and deployed behavior were not verified.

### Next step

The manager prepares the release PR with both required approvers. No deployment is authorized by this branch.
