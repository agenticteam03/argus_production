import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

let user = null;
vi.mock("../context/AuthContext.jsx", () => ({ useAuth: () => ({ user, loginPrivate: vi.fn(), refresh: vi.fn() }) }));
vi.mock("../services/index.js", () => ({ argus: { getApproval: vi.fn() }, secondFactor: { confirmLogin: vi.fn() } }));
const { default: IncidentApproval } = await import("./IncidentApproval.jsx");

const waiting = { approval: { id: "apr_1", state: "pending" } };
const html = (action) => renderToStaticMarkup(<IncidentApproval action={action} onAnswered={() => {}} />);
const APPROVER = { role: "approver", access: "investigate", actions: ["view_incidents"] };

describe("IncidentApproval", () => {
  it("appears only while the incident's approval waits, and only for an approver", () => {
    user = APPROVER;
    expect(html(null)).toBe("");
    expect(html({ approval: null })).toBe("");
    expect(html({ approval: { id: "apr_1", state: "approved" } })).toBe("");
    user = { role: "operator", access: "investigate", actions: ["view_incidents"] };
    expect(html(waiting)).toBe("");
    user = { role: "viewer", access: "read", actions: [] };
    expect(html(waiting)).toBe("");
  });

  it("leads an approver through the private login and the security key, as on Actions", () => {
    user = APPROVER;
    expect(html(waiting)).toContain("Private sign-in");
    user = { ...APPROVER, access: "ops", secondFactor: { verified: false } };
    const key = html(waiting);
    expect(key).toContain("Use security key");
    expect(key).not.toContain("Private sign-in");
  });

  it("loads the frozen card once the decisions are granted", () => {
    user = { ...APPROVER, access: "ops", actions: ["approve_action"], secondFactor: { verified: true } };
    const out = html(waiting);
    expect(out).toContain("animate-pulse");
    expect(out).not.toContain("Private sign-in");
    expect(out).not.toContain("Use security key");
  });
});
