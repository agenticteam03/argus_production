import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import WhyCard from "./WhyCard.jsx";

const API = "vm-166/container:argus-lab-api";
const CACHE = "vm-166/container:argus-lab-cache";
const decided = (by) => [{ node: "investigate", phase: "exit", data: { decided_by: by } }];

const html = ({ incident, events = [], cited = [] }) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <WhyCard incident={incident} events={events} cited={cited} onJump={() => {}} />
    </MemoryRouter>,
  );

describe("WhyCard", () => {
  it("draws the chain from the alerted target to a different root cause", () => {
    const out = html({ incident: { target: API, root_cause_target: CACHE } });
    expect(out).toContain("argus-lab-api");
    expect(out).toContain("argus-lab-cache");
    expect(out).toContain("root cause");
    expect(out).not.toContain("is the root cause");
  });

  it("says the target itself is the root cause when both are the same", () => {
    expect(html({ incident: { target: API, root_cause_target: API } })).toContain("is the root cause");
  });

  it("names who decided: the rules (no AI) or the AI, and the AI calls only when the backend reports them", () => {
    const rules = html({ incident: { target: API, model_calls: 0 }, events: decided("baseline") });
    expect(rules).toContain("Rules (no AI)");
    expect(rules).toContain("AI calls");
    expect(html({ incident: { target: API }, events: decided("model") })).toContain(">AI<");
    expect(html({ incident: { target: API } })).not.toContain("AI calls");
  });

  it("lists the findings, or says there are none", () => {
    expect(html({ incident: { target: API, findings: ["cache stopped", "api errors"] } })).toContain("<li>api errors</li>");
    expect(html({ incident: { target: API } })).toContain("No findings recorded.");
  });

  it("counts the causes ruled out, singular and plural", () => {
    expect(html({ incident: { target: API, ruled_out: ["the network"] } })).toContain("1 other cause ruled out");
    expect(html({ incident: { target: API, ruled_out: ["a", "b"] } })).toContain("2 other causes ruled out");
  });

  it("links a cited evidence record it has, and shows an unknown id as plain text", () => {
    const evidence = [{ evidence_id: "ev_0123456789abcdef", capability: "container.status", target: CACHE, model_text: "exited (0)\nmore" }];
    const out = html({ incident: { target: API, evidence }, cited: ["ev_0123456789abcdef", "ev_missing"] });
    expect(out).toContain("Evidence it cites");
    expect(out).toContain("argus-lab-cache · exited (0)");
    expect(out).toMatch(/<a [^>]*href="\/\?tab=evidence#evidence-ev_0123456789abcdef"/);
    expect(out).toContain("ev_missing");
  });

  it("shows the full diagnosis only when it says more than its first sentence", () => {
    expect(html({ incident: { target: API, diagnosis: "One sentence." } })).not.toContain("Full diagnosis");
    expect(html({ incident: { target: API, diagnosis: "One sentence. And more detail." } })).toContain("Full diagnosis");
  });
});
