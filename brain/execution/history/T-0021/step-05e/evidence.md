# T-0021 step 05e — evidence (2026-10-09, juanbetancurm, session 9123f9010669)

Goal: on vm-095, deploy the review fixes of PR #36 (`6f45218`): the tools-server launcher runs `cd /` and
`python -I -u`, and `isolation_check` probes a package planted in the caller's folder (ARCHITECTURE §12.6,
ACR-0002). vm-166 was not touched. `code.bash` here holds the blocks that ran.

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).

| Part | Observed | Result |
|---|---|---|
| L.1 lease | `conantkd`'s lease released; `Lease CLAIMED by juanbetancurm`; vm-095 marker `holder=juanbetancurm` | OK |
| deploy | `SESSION OK`; baseline saved; `DEPLOY OK: 6f452188813b (task/T-0021-tool-isolation)`; agent, worker, scheduler rebuilt and running; `LAB BASELINE OK` | OK |
| worker | `catalogue=mcp`; the launcher in the image: `cd / \|\| exit 1`, `exec /usr/local/bin/python -I -u -m argus.tooling.mcp.tools_server` | OK |
| isolation check | 7 lines `ok`: no token readable (7 expected by the inventory); the sudo launcher; sudo refuses `cat` of a token, an extra argument and `true`; **the launcher ignores code planted in the caller's folder: the fake argus package did not run**; the tools process lists 16 capabilities | **TOOLS ISOLATION OK** |
| after | `NO INTERFERENCE: non-Argus objects unchanged` | OK |

**Result:** step 5e done. vm-095 runs `task/T-0021-tool-isolation` `6f45218` with the worker in `mcp` mode and the
fixed launcher; the hole found in the review of PR #36 is closed on the VM.

**State to keep in mind:** PR #36 was merged into `main` (`a9b4df8`) at its earlier head `289bb0d`, before this
fix and before the re-review. `main` therefore has the OLD launcher. **Do not deploy `main` on vm-095** until the
follow-up PR with these fixes merges: it would bring back the launcher that runs a planted package as
`argus-tools`. vm-095's `hosts.env` keeps `ARGUS_TOOL_CATALOGUE=mcp`.
