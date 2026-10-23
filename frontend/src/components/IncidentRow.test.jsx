import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import IncidentRow from "./IncidentRow.jsx";

const inc = (over = {}) => ({
  id: "inc_1a2b3c4d", target: "vm-166/container:argus-lab-api", status: "closed", outcome: "diagnosed",
  root_cause_target: "vm-166/container:argus-lab-cache", opened_at: "2026-10-22T03:00:00Z",
  class: "dependency_unavailable", strategy: "model", ...over,
});
const html = (incident, compact) =>
  renderToStaticMarkup(<MemoryRouter><IncidentRow incident={incident} compact={compact} /></MemoryRouter>);

describe("IncidentRow", () => {
  it("links to the incident page and shows its target, status and outcome", () => {
    const out = html(inc());
    expect(out).toContain('href="/incidents/inc_1a2b3c4d"');
    for (const s of ["argus-lab-api", "Closed", "Diagnosed", "Root cause: argus-lab-cache"]) expect(out).toContain(s);
    expect(out).toContain('dateTime="2026-10-22T03:00:00Z"');
  });

  it("shows class and strategy in the list, a dash when missing, and neither in the compact card", () => {
    expect(html(inc())).toContain("dependency_unavailable · model");
    expect(html(inc({ class: null, strategy: undefined }))).toContain("— · —");
    expect(html(inc(), true)).not.toContain("dependency_unavailable");
  });

  it("says a queued incident is waiting rather than giving it an outcome", () => {
    const out = html(inc({ status: "queued", outcome: null }));
    expect(out).toContain("Waiting to start");
    expect(out).toContain("No outcome yet");
  });
});
