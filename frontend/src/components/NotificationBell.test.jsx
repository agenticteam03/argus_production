import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { NotificationBellView } from "./NotificationBell.jsx";

const html = (props) => renderToStaticMarkup(<MemoryRouter><NotificationBellView {...props} /></MemoryRouter>);

describe("NotificationBell (ACR-0042)", () => {
  it("shows no badge without a count or with none waiting", () => {
    expect(html({ count: null, items: null })).not.toContain("bg-red-500");
    expect(html({ count: null, items: null })).toContain("No notifications.");
    const none = html({ count: 0, items: null });
    expect(none).not.toContain("bg-red-500");
    expect(none).toContain("No approval is waiting for you.");
  });

  it("badges the count and leads to Actions", () => {
    const out = html({ count: 2, items: null });
    expect(out).toContain('aria-label="Notifications: 2 approvals waiting"');
    expect(out).toMatch(/bg-red-500[^>]*>2</);
    expect(out).toContain('href="/actions"');
    expect(html({ count: 1, items: null })).toContain("1 approval is waiting for you.");
    expect(html({ count: 50, items: null })).toContain("50+");
  });

  it("names each approval only when the private list is read, linking to its incident", () => {
    const items = [{ id: "apr_1", incident_id: "inc_9", capability: "container.start", target: "vm-166/container:api",
      risk: "amber", verdict: "doubt", expires_at: "2026-10-28T23:00:00Z" }];
    const out = html({ count: 1, items });
    expect(out).toContain('href="/incidents/inc_9"');
    expect(out).toContain("container.start");
    expect(out).toContain("judge doubted");
    expect(html({ count: 1, items: null })).not.toContain("container.start");
  });
});
