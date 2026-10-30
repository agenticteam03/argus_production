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

  it("badges only the unread ones and offers to mark them all read (T-0016)", () => {
    const read = html({ count: 2, items: null, unread: 0 });
    expect(read).not.toContain("bg-red-500");
    expect(read).not.toContain("Mark all as read");
    expect(read).toContain("2 approvals are waiting for you.");
    const fresh = html({ count: 2, items: null, unread: 1 });
    expect(fresh).toMatch(/bg-red-500[^>]*>1</);
    expect(fresh).toContain("Mark all as read");
    expect(fresh).toContain('aria-label="Notifications: 1 unread of 2 approvals waiting"');
  });

  it("marks which approvals are still unread when the private list names them", () => {
    const items = [{ id: "apr_1", incident_id: "inc_9", capability: "container.start", target: "t", risk: "amber" },
      { id: "apr_2", incident_id: "inc_8", capability: "network.restore", target: "t", risk: "green" }];
    const out = html({ count: 2, items, unread: 1, unreadIds: ["apr_2"] });
    expect(out.match(/aria-label="Unread"/g)).toHaveLength(1);
  });
});
