import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import PendingApprovals from "./PendingApprovals.jsx";

const items = [
  { id: "appr_1", incident_id: "inc_1", capability: "container.start", target: "vm-166/container:argus-lab-cache",
    risk: "red", verdict: "agree", expires_at: "2099-01-01T00:00:00Z" },
];

describe("PendingApprovals", () => {
  it("lists each pending approval with its action, target, risk and an open control", () => {
    const out = renderToStaticMarkup(<PendingApprovals items={items} onOpen={() => {}} />);
    for (const text of ["container.start", "vm-166/container:argus-lab-cache", "Red risk", "appr_1", "Open"])
      expect(out).toContain(text);
  });

  it("marks an approval the judge doubted (ACR-0039)", () => {
    const doubted = [{ ...items[0], verdict: "doubt", risk: "amber" }];
    expect(renderToStaticMarkup(<PendingApprovals items={doubted} onOpen={() => {}} />)).toContain("Judge doubted");
    expect(renderToStaticMarkup(<PendingApprovals items={items} onOpen={() => {}} />)).not.toContain("Judge doubted");
  });

  it("says so when nothing waits", () => {
    expect(renderToStaticMarkup(<PendingApprovals items={[]} onOpen={() => {}} />)).toContain("No approval is waiting");
  });
});
