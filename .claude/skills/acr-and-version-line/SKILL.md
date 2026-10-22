---
name: acr-and-version-line
description: >-
  Draft an Argus Architecture Change Record and reconcile ARCHITECTURE.md
  version metadata when accepted architecture changes from parallel branches
  meet. Use for an actual architecture change, not routine code or task edits.
---

# ACR and architecture version line

Read `brain/agents/AGENT_PROTOCOL.md` §4 and
`brain/architecture/changes/ACR-TEMPLATE.md` before drafting. The template is
the source for ACR fields and sections; do not maintain a copied form here.
`brain/architecture/ARCHITECTURE.md` is authoritative for the current design.

1. For a proposal, find the next free ACR number in the repository and open
   PRs. Copy the template to `brain/architecture/changes/ACR-NNNN-<slug>.md`.
   Fill evidence, the exact architecture section, smallest change, an
   alternative, consequences, and open decisions. Keep status `proposed` and
   leave the architecture document unchanged until the human decision required
   by the Brain protocol. A safety-principle change also needs the protocol's
   second approval.
2. When an ACR is accepted, record the human decision in the ACR. In the
   implementation PR, change the agreed architecture sections, bump to a free
   version, add the ACR-linked changelog row, and include the first code that
   needs the change. An ACR may cover multiple implementation versions; read
   the existing rows before assigning the next number. Editing the version
   line never accepts an ACR or supplies a review.
3. If two branches touched the version line or changelog, save each reviewed
   `ARCHITECTURE.md` snapshot and run:

   ```text
   python .claude/skills/acr-and-version-line/scripts/version_line.py --current <current-architecture> --incoming <other-architecture>
   ```

   The read-only helper prints a replacement version value in descending
   numeric order and complete changelog rows in ascending numeric order. It
   refuses a missing row/link or different content assigned to the same
   version. Resolve a collision with the reviewer and assign a free version;
   rerun on the revised snapshots. Apply the printed metadata alongside the
   reviewed *section content*; the helper does not merge architecture prose.
   Inspect the final diff against both inputs so neither change is lost. The
   current changelog has `1.8.5` before `1.8.4`; the first run will reorder
   those existing rows without changing or dropping either payload.
4. Run the relevant tests, Brain lint/audit and `git diff --check`. Have the
   protected architecture/skill paths reviewed under
   `brain/agents/REVIEW_PROTOCOL.md`; use the current `code.bash` procedure
   for any developer action. The helper does not write files, approve, merge,
   push, deploy or access a VM.
