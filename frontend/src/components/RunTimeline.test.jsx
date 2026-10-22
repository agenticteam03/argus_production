import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import RunTimeline from "./RunTimeline.jsx";

const ev = (node, phase, at, data = {}) => ({ node, phase, at: `2026-10-21T12:00:${at}Z`, data });
const html = (props) =>
  renderToStaticMarkup(<RunTimeline incident={{}} events={[]} active={false} reconnecting={false} evidenceIds={new Set()} onJump={() => {}} {...props} />);

describe("RunTimeline", () => {
  it("says what it waits for while active, and that nothing was recorded once final", () => {
    expect(html({ active: true })).toContain("Waiting for the first event…");
    expect(html({ active: false })).toContain("No events were recorded.");
  });

  it("labels each stage and sums the run: duration, reads and AI calls", () => {
    const events = [
      ev("detect", "enter", "00"), ev("detect", "exit", "01"),
      ev("investigate", "enter", "01"),
      ev("investigate", "step", "03", { capability: "container.status", target: "vm-166/container:argus-lab-cache", evidence_id: "ev_1" }),
      ev("investigate", "step", "05", { capability: "container.logs", target: "vm-166/container:argus-lab-api", status: "timeout" }),
      ev("investigate", "exit", "06"),
    ];
    const out = html({ incident: { model_calls: 0 }, events, evidenceIds: new Set(["ev_1"]) });
    expect(out).toContain("Detect");
    expect(out).toContain("Investigate");
    expect(out).toContain("Finished · 6.0 s · 2 reads · no AI calls");
    expect(out).toMatch(/<button[^>]*>container\.status argus-lab-cache<\/button>/);   // a read with its evidence jumps
    expect(out).toContain("container.logs argus-lab-api · timeout");                    // one without: plain text
  });

  it("counts one AI call in the singular, and leaves the calls out when the backend does not report them", () => {
    const events = [ev("investigate", "enter", "00"), ev("investigate", "exit", "02")];
    expect(html({ incident: { model_calls: 1 }, events })).toContain("0 reads · 1 AI call");
    expect(html({ incident: {}, events })).not.toContain("AI call");
  });
});
