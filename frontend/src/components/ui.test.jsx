import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ErrorCard, Fact, LivePill, OutcomeBadge, Segmented, StatusBadge, TabList, TabPanel } from "./ui.jsx";

const html = (el) => renderToStaticMarkup(el);

describe("StatusBadge and OutcomeBadge", () => {
  it("names each documented status and only a running one pulses", () => {
    expect(html(<StatusBadge status="running" />)).toContain("Running");
    expect(html(<StatusBadge status="running" />)).toContain("animate-pulse");
    expect(html(<StatusBadge status="closed" />)).not.toContain("animate-pulse");
    expect(html(<StatusBadge status="escalated" />)).toContain("Escalated");
  });

  it("shows an unknown status as it came, and a missing one as Unknown, never as a known state", () => {
    expect(html(<StatusBadge status="paused" />)).toContain("paused");
    expect(html(<StatusBadge />)).toContain("Unknown");
  });

  it("says when there is no outcome yet instead of implying one", () => {
    expect(html(<OutcomeBadge outcome={null} />)).toContain("No outcome yet");
    expect(html(<OutcomeBadge outcome="diagnosed" />)).toContain("Diagnosed");
    expect(html(<OutcomeBadge outcome="refused" />)).toContain("text-red-300");
    expect(html(<OutcomeBadge outcome="something_new" />)).toContain("something_new");
  });
});

describe("LivePill", () => {
  it("labels demo data as demo, even while polling", () => {
    const out = html(<LivePill live source="demo" />);
    expect(out).toContain("Demo data");
    expect(out).not.toContain("animate-pulse");
  });

  it("pulses only while live, and says Reconnecting when not", () => {
    expect(html(<LivePill live source="api" />)).toContain("animate-pulse");
    const stale = html(<LivePill live={false} source="api" />);
    expect(stale).toContain("Reconnecting");
    expect(stale).not.toContain("animate-pulse");
  });

  it("shows the last refresh only when there was one, in a readable colour", () => {
    expect(html(<LivePill live source="api" />)).not.toContain("updated");
    const out = html(<LivePill live source="api" at={Date.UTC(2026, 9, 22, 4, 0, 0)} />);
    expect(out).toContain("· updated");
    expect(out).not.toContain("text-muted/60");                  // OP-014 step 12: AA contrast
  });
});

describe("Fact", () => {
  it("shows a dash for a missing value, never an empty cell", () => {
    expect(html(<Fact label="Root cause" />)).toContain("—");
    expect(html(<Fact label="Root cause">cache</Fact>)).toContain("cache");
  });
});

describe("Segmented", () => {
  it("marks only the chosen option as pressed", () => {
    const out = html(<Segmented label="Range" value="6h" onChange={() => {}}
      options={[{ value: "1h", label: "1 h" }, { value: "6h", label: "6 h" }]} />);
    expect(out).toContain('aria-label="Range"');
    expect(out.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(out).toMatch(/aria-pressed="true"[^>]*>6 h</);
  });
});

describe("TabList and TabPanel", () => {
  const tabs = [{ id: "answer", label: "Answer" }, { id: "evidence", label: "Evidence", count: 4 }];

  it("selects one tab and keeps only it in the tab order (roving tabindex)", () => {
    const out = html(<TabList label="Incident" tabs={tabs} value="evidence" onChange={() => {}} />);
    expect(out.match(/aria-selected="true"/g)).toHaveLength(1);
    expect(out).toMatch(/id="tab-evidence"[^>]*aria-selected="true"[^>]*tabindex="0"/);
    expect(out).toMatch(/id="tab-answer"[^>]*aria-selected="false"[^>]*tabindex="-1"/);
    expect(out).toContain(">4</span>");
  });

  it("renders a panel only for the selected tab, labelled by it", () => {
    expect(html(<TabPanel id="answer" value="evidence">A</TabPanel>)).toBe("");
    const out = html(<TabPanel id="evidence" value="evidence">E</TabPanel>);
    expect(out).toContain('role="tabpanel"');
    expect(out).toContain('aria-labelledby="tab-evidence"');
  });
});

describe("ErrorCard", () => {
  it("is announced as an alert and offers Retry only when it can retry", () => {
    expect(html(<ErrorCard title="Could not load" text="The API did not answer." />)).toContain('role="alert"');
    expect(html(<ErrorCard title="x" text="y" />)).not.toContain("Retry");
    expect(html(<ErrorCard title="x" text="y" onRetry={() => {}} />)).toContain("Retry");
  });
});
