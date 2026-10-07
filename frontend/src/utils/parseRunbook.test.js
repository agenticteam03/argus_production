import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseRunbook } from "./parseRunbook.js";

const demoDir = join(dirname(fileURLToPath(import.meta.url)), "../services/demoRunbooks");

const FIXTURE = `# RB-999 — Fixture runbook

## Metadata

\`\`\`yaml
id: RB-999
title: Fixture incident
status: draft
owner: Argus Team
version: 2.1.0
last_reviewed: 2026-10-01
detector: fixture_detector
\`\`\`

## Scope

Hosts of type \`lab\` only. See [conventions](../RUNBOOK-CONVENTIONS.md) for the rest.

## Incident definition

Something breaks repeatedly. \`code=137\` appears. The operator notices.

## Required Argus tools

| Tool / expected input | Purpose / relevant output | Safety class |
|---|---|---|
| \`get_container_status(container\`) | State and exit code | \`READ_ONLY_SAFE\` |
| \`restart_container(container)\` | Restarts it | \`MUTATING_APPROVED\` |
| \`delete_volume(volume)\` | Deletes data | \`HIGH_RISK_REQUIRES_APPROVAL\` |

One more line.

## Notes

MISSING TOOL REQUIREMENT: \`collect_memory_history\`.
MISSING TOOL REQUIREMENT: \`read_kernel_logs\`.
`;

describe("parseRunbook", () => {
  it("extracts the metadata block", () => {
    const rb = parseRunbook({ file: "RB-999.md", markdown: FIXTURE });
    expect(rb.id).toBe("RB-999");
    expect(rb.title).toBe("Fixture incident");
    expect(rb.version).toBe("2.1.0");
    expect(rb.status).toBe("draft");
    expect(rb.owner).toBe("Argus Team");
    expect(rb.lastReviewed).toBe("2026-10-01");
    expect(rb.detector).toBe("fixture_detector");
  });

  it("classifies risk from the tools table: high-risk beats mutating beats read-only", () => {
    const rb = parseRunbook({ file: "RB-999.md", markdown: FIXTURE });
    expect(rb.risk).toBe("high");
  });

  it("classifies mutating risk when no tool is high-risk", () => {
    const md = FIXTURE.replace("HIGH_RISK_REQUIRES_APPROVAL", "READ_ONLY_SAFE");
    expect(parseRunbook({ file: "x.md", markdown: md }).risk).toBe("mutating");
  });

  it("classifies read-only risk when only read tools are present", () => {
    const md = FIXTURE
      .replaceAll("MUTATING_APPROVED", "READ_ONLY_SAFE")
      .replaceAll("HIGH_RISK_REQUIRES_APPROVAL", "READ_ONLY_SAFE");
    expect(parseRunbook({ file: "x.md", markdown: md }).risk).toBe("read-only");
  });

  it("returns a risk value the UI badge always understands", () => {
    // RunbookCard destructures RISK[rb.risk]; an unknown key would crash the page.
    for (const md of [FIXTURE, "no metadata at all", "# Just a title"]) {
      expect(["read-only", "mutating", "high"]).toContain(parseRunbook({ file: "x.md", markdown: md }).risk);
    }
  });

  it("extracts tool names and safety classes, skipping header and separator rows", () => {
    const rb = parseRunbook({ file: "RB-999.md", markdown: FIXTURE });
    expect(rb.tools).toEqual([
      { name: "get_container_status", safety: "READ_ONLY_SAFE" },
      { name: "restart_container", safety: "MUTATING_APPROVED" },
      { name: "delete_volume", safety: "HIGH_RISK_REQUIRES_APPROVAL" },
    ]);
  });

  it("counts MISSING TOOL REQUIREMENT mentions", () => {
    expect(parseRunbook({ file: "RB-999.md", markdown: FIXTURE }).missing).toBe(2);
  });

  it("cleans markdown out of the summary and scope sentences", () => {
    const rb = parseRunbook({ file: "RB-999.md", markdown: FIXTURE });
    expect(rb.summary).toBe("Something breaks repeatedly. code=137 appears.");
    expect(rb.scope).toBe("Hosts of type lab only.");
  });

  it("falls back to the filename and H1 when metadata is missing", () => {
    const rb = parseRunbook({ file: "orphan.md", markdown: "# Orphan runbook\n\nNothing else." });
    expect(rb.id).toBe("orphan.md");
    expect(rb.title).toBe("Orphan runbook");
    expect(rb.version).toBeUndefined();
  });

  it("survives empty markdown without throwing", () => {
    const rb = parseRunbook({ file: "empty.md", markdown: "" });
    expect(rb.id).toBe("empty.md");
    expect(rb.tools).toEqual([]);
  });

  it("parses the shipped demo runbook RB-001 end to end", () => {
    const markdown = readFileSync(join(demoDir, "RB-001-container-oom-restart-loop.md"), "utf8");
    const rb = parseRunbook({ file: "RB-001-container-oom-restart-loop.md", markdown });
    expect(rb.id).toBe("RB-001");
    expect(rb.version).toBe("1.0.0");
    expect(rb.detector).toBe("oom_restart_loop");
    expect(rb.risk).toBe("high");
    expect(rb.missing).toBe(4);
    expect(rb.tools).toHaveLength(12);
  });
});
