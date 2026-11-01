// T-0016 motion: which shared pieces carry which animation (the animations themselves are tokens in src/motion.css,
// tested in src/motion.test.js; the browser checks are in e2e/motion.e2e.js).
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import ConsolePanel from "./console/ConsolePanel.jsx";
import SystemMap from "./map/SystemMap.jsx";
import { NotificationBellView } from "./NotificationBell.jsx";
import { Card, CountUp, Disclosure, ErrorCard, Hint, LivePill, Select, Skeleton, TabList, TabPanel, Toast } from "./ui.jsx";

const html = (el) => renderToStaticMarkup(<MemoryRouter>{el}</MemoryRouter>);

describe("loading skeletons", () => {
  it("shimmer instead of blinking, and stay out of the accessibility tree", () => {
    const out = html(<Skeleton className="h-24" />);
    expect(out).toContain("skeleton");
    expect(out).toContain('aria-hidden="true"');
    expect(out).toContain("h-24");
    expect(out).not.toContain("animate-pulse");
  });
});

describe("counters and badges", () => {
  it("a card's count pops in again whenever it changes", () => {
    expect(html(<Card title="Incidents" count={3}>x</Card>)).toMatch(/animate-pop[^>]*>3</);
  });

  it("a tab's count pops in too", () => {
    expect(html(<TabList label="Incident" tabs={[{ id: "e", label: "Evidence", count: 4 }]} value="e" onChange={() => {}} />)).toMatch(/animate-pop[^>]*>4</);
  });

  it("CountUp renders the final number when there is nothing to animate (a server render, reduced motion)", () => {
    const out = html(<CountUp value={7} />);
    expect(out).toMatch(/tabular-nums[^>]*>7</);
    expect(html(<CountUp value="—" />)).toContain("—");
  });

  it("the bell's badge pops and the bell rings while approvals wait; its list drops in", () => {
    const out = html(<NotificationBellView count={2} items={null} />);
    expect(out).toMatch(/animate-pop[^>]*>2</);
    expect(out).toContain("animate-ring");
    expect(out).toContain("menu-pop");
    expect(html(<NotificationBellView count={0} items={null} />)).not.toContain("animate-ring");
  });
});

describe("panels, menus and messages", () => {
  it("a tab's panel fades in when it is chosen", () => {
    expect(html(<TabPanel id="a" value="a">A</TabPanel>)).toContain("animate-fade-in");
  });

  it("a disclosure's body rises in when it opens", () => {
    expect(html(<Disclosure summary="More">body</Disclosure>)).toContain("group-open:animate-rise");
  });

  it("a tooltip fades in when shown", () => {
    expect(html(<Hint text="Explained">term</Hint>)).toMatch(/role="tooltip"[^>]*animate-fade-in|animate-fade-in[^>]*role="tooltip"/);
  });

  it("the themed select's chevron turns as it opens (its list drops in, checked in the browser)", () => {
    expect(html(<Select value="a" onChange={() => {}} aria-label="Pick"><option value="a">A</option></Select>)).toContain("transition-transform");
  });

  it("an error card rises in, a toast slides in, and both keep their roles", () => {
    const err = html(<ErrorCard title="x" text="y" />);
    expect(err).toContain('role="alert"');
    expect(err).toContain("animate-rise");
    const toast = html(<Toast onDone={() => {}}>Saved</Toast>);
    expect(toast).toContain('role="status"');
    expect(toast).toContain("toast-in");
  });

  it("the system map shimmers while ELK lays it out, and still says so in words", () => {
    const topology = { hosts: [{ id: "vm-166", role: "monitored" }], nodes: [{ id: "a", host: "vm-166", label: "a", kind: "container", health: "healthy" }], edges: [] };
    const out = html(<SystemMap topology={topology} />);
    expect(out).toContain("skeleton");
    expect(out).toContain("Laying out dependencies…");
  });

  it("the console panel's activity and suggestions come in one after another", () => {
    const history = [{ command_id: "c1", input: "cache status", status: "ok", output: [], by: "olga", started_at: "2026-10-29T10:44:00Z" }];
    const out = html(<ConsolePanel incident={{ id: "inc_1", status: "closed" }} history={history} now={Date.parse("2026-10-29T10:46:00Z")} />);
    expect(out).toMatch(/<ol[^>]*stagger/);
  });

  it("the Live dot stops pulsing with reduced motion", () => {
    expect(html(<LivePill live source="api" />)).toMatch(/animate-pulse[^"]*motion-reduce:animate-none|motion-reduce:animate-none[^"]*animate-pulse/);
  });
});
