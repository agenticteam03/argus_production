import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import RunbookCard from "./RunbookCard.jsx";

const tool = (name, safety = "READ_ONLY_SAFE") => ({ name, safety });
const rb = (over = {}) => ({
  id: "RB-003", title: "Dependency unavailable", status: "active", version: "1.2", risk: "read-only",
  summary: "Find which dependency failed first.", detector: "dependency_unavailable", scope: "containers",
  missing: 0, tools: [], ...over,
});
const html = (runbook) => renderToStaticMarkup(<RunbookCard runbook={runbook} onOpen={() => {}} />);

describe("RunbookCard", () => {
  it("shows the id, version, status, title and the risk label", () => {
    const out = html(rb({ risk: "high" }));
    for (const s of ["RB-003", "v1.2", "active", "Dependency unavailable", "High-risk action"]) expect(out).toContain(s);
  });

  it("lists mutating tools first, so a risky step is never hidden behind '+N more'", () => {
    const out = html(rb({ tools: [tool("a"), tool("b"), tool("c"), tool("restart", "MUTATING_LOW")] }));
    expect(out.indexOf("restart")).toBeLessThan(out.indexOf(">a<"));
    expect(out).toContain("+1 more");
    expect(out).not.toContain(">c<");
  });

  it("warns how many tools are missing, singular and plural", () => {
    expect(html(rb())).not.toContain("missing");
    expect(html(rb({ missing: 1 }))).toContain("1 missing tool<");
    expect(html(rb({ missing: 2 }))).toContain("2 missing tools");
  });

  it("falls back to explicit placeholders instead of blank fields", () => {
    const out = html(rb({ summary: "", detector: null, scope: "", version: null }));
    expect(out).toContain("No summary available.");
    expect(out.match(/—/g)).toHaveLength(2);
    expect(out).not.toContain(">v");
  });
});
