import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

let user = null;
vi.mock("../context/AuthContext.jsx", () => ({ useAuth: () => ({ user }) }));
vi.mock("../services/index.js", () => ({ argus: { resolveIncident: vi.fn() } }));
const { default: ResolveIncident, Resolution } = await import("./ResolveIncident.jsx");

const escalated = { id: "inc_1", status: "escalated" };
const html = (incident) => renderToStaticMarkup(<ResolveIncident incident={incident} onResolved={() => {}} />);

describe("ResolveIncident (ACR-0041)", () => {
  it("shows Resolve only on an escalated incident and only when /me lists resolve_incident", () => {
    user = { actions: ["view_incidents", "resolve_incident"] };
    expect(html(escalated)).toContain(">Resolve<");
    expect(html({ ...escalated, status: "closed" })).toBe("");
    expect(html({ ...escalated, status: "running" })).toBe("");
    user = { actions: ["view_incidents"] };
    expect(html(escalated)).toBe("");
    user = null;
    expect(html(escalated)).toBe("");
  });

  it("shows who resolved it, when and why", () => {
    const out = renderToStaticMarkup(<Resolution resolution={{ by: "olga", at: "2026-10-28T20:00:00Z", reason: "restarted by hand" }} />);
    for (const text of ["Resolved by", "olga", "restarted by hand"]) expect(out).toContain(text);
    expect(renderToStaticMarkup(<Resolution resolution={null} />)).toBe("");
  });
});
