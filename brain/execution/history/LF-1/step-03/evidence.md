# LF-1 step 03 — fresh baseline under the explicitly authorized shared lease

Status: executed and verified. The user explicitly authorized using conantkd's lease shared with the other agent. The existing marker dc432c3ff537 and AFTER-MERGE-main task were preserved; no new lease was claimed or the other task's lease released.

- vm-095 deployed commit 46ba3a3, task/AFTER-MERGE-main-2026-10-14; checkout clean. The concurrent task's deployment explains the change from step 01.
- RAM: 5900 MiB total, 4407 MiB available, no swap. Free disk: 73649 MiB.
- Five existing core services (including UI): running, restarts 0, OOM false.
- /healthz: 10/10 HTTP 200; 2.15–2.63 ms.
- LAB BASELINE OK; NO INTERFERENCE.

The trial has no agent rebuild or real-data ingestion. The production service state will be compared before and after the temporary stack. Sharing was directly authorized by the human user; this does not authorize releasing the other agent's lease.