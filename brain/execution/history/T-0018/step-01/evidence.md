# T-0018 step 01 — evidence (2026-10-06, run by conantkd, session 796fd4f3bf61)

Goal: before creating the SC-07 lab network `argus-lab-iso`, prove that `172.30.3.0/24` is free on vm-166.

Key output lines from output.bash, SANITIZED (no addresses of the VMs, no secrets, no personal names). The Docker
ranges below are private container ranges, not VM addresses.

| Check | Expected | Observed | Result |
|---|---|---|---|
| S.0 session marker | `holder=conantkd session=796fd4f3bf61` | the same line | OK |
| session / code | `SESSION OK`; on `main` | `SESSION OK`; `commit=2097eb155cc8…`, `ref=main`; `LAB BASELINE OK` | OK |
| Docker networks | Argus `172.30.1.0/24`, `172.30.2.0/24` + non-Argus ones | `argus-v18-mon 172.30.1.0/24`, `argus-lab-app 172.30.2.0/24`; non-Argus: `bridge 172.17.0.0/16`, `monitoring_default 172.18.0.0/16`, `labmvp_default 172.19.0.0/16`, `gateways_default 172.20.0.0/16`, `probes_default 172.21.0.0/16`, `host`, `none` | OK |
| host addresses / routes in 172.16.0.0/12 | only the bridges above | one bridge per network above, routes `172.17`–`172.21` and `172.30.1`, `172.30.2`; nothing in `172.30.3` | OK |
| verdict | `SUBNET FREE` | `SUBNET FREE: 172.30.3.0/24 is not used on vm-166` | OK |
| nonint-check after | `NO INTERFERENCE` | `NO INTERFERENCE: non-Argus objects unchanged` | OK |

nonint-check: NO INTERFERENCE on vm-166 (yes).

**Result:** `argus-lab-iso` can use `172.30.3.0/24` on vm-166 without overlapping any network of the protected
deployment (`172.17`–`172.21`) or of Argus (`172.30.1`, `172.30.2`).
