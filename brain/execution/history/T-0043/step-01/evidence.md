# T-0043 step 1 — evidence (2026-10-13 UTC, conantkd's agent over ssh; both leases, session 4f8a9d4f8dc1)

Read-only checks on vm-095 of the branch's files (`e3b503b`, fetched into the checkout's git and exported to `/tmp`;
`checkout local modifications: 0`; `/tmp` removed), with the Prometheus image the hosts run (`prom/prometheus:v3.5.0`):

| Check | Observed | Result |
|---|---|---|
| `promtool check config --syntax-only` vm-095 | `SUCCESS: … is valid prometheus config file syntax` | OK |
| `promtool check config --syntax-only` vm-166 | `SUCCESS` | OK |
| `promtool check rules alerts.yml` | `SUCCESS: 9 rules found` (8 of `main` + `ArgusScrapeTargetMissing`) | OK |
| `promtool test rules tests/promql/op005_test.yml` | `SUCCESS` (with the new case: a missing job + a job down = 2) | OK |
| the new `scrape_targets_down` on vm-095's live Prometheus | `0` | OK (everything scraped) |
| the same on vm-166's (through the tunnel) | `0` | OK |

No service was changed; the rule and the external labels take effect when the AFTER-MERGE recreates
`argus-v18-prometheus` on both hosts.
