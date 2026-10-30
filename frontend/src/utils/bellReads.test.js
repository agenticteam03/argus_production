import { describe, expect, it } from "vitest";
import { markAllRead, markRead, NOTHING_SEEN, reconcile, unreadCount } from "./bellReads.js";

const item = (id) => ({ id, incident_id: `inc_${id}` });

describe("the bell's read state (per person, in this browser)", () => {
  it("counts every waiting approval as unread until it is seen", () => {
    expect(unreadCount({ count: 2, items: null }, NOTHING_SEEN)).toBe(2);
    expect(unreadCount({ count: 2, items: [item("a"), item("b")] }, NOTHING_SEEN)).toBe(2);
    expect(unreadCount({ count: null, items: null }, NOTHING_SEEN)).toBe(0);
  });

  it("marks one approval read when it is opened, and all of them at once", () => {
    const state = { count: 2, items: [item("a"), item("b")] };
    const one = markRead(NOTHING_SEEN, state, "a");
    expect(unreadCount(state, one)).toBe(1);
    expect(unreadCount(state, markAllRead(state))).toBe(0);
  });

  it("with only the count (an ordinary session), reading clears what is waiting now, and a new one shows again", () => {
    const seen = markAllRead({ count: 1, items: null });
    expect(unreadCount({ count: 1, items: null }, seen)).toBe(0);
    expect(unreadCount({ count: 2, items: null }, seen)).toBe(1);
    expect(unreadCount({ count: 1, items: null }, markRead(NOTHING_SEEN, { count: 1, items: null }, null))).toBe(0);
  });

  it("forgets what was decided: when fewer wait, a later new one is unread", () => {
    const seen = reconcile(markAllRead({ count: 3, items: null }), { count: 1, items: null });
    expect(seen.count).toBe(1);
    expect(unreadCount({ count: 2, items: null }, seen)).toBe(1);
    const ids = reconcile(markAllRead({ count: 2, items: [item("a"), item("b")] }), { count: 1, items: [item("b")] });
    expect(ids.ids).toEqual(["b"]);
  });

  it("keeps what was read when the private session starts naming the approvals (the same ones, not new)", () => {
    const seen = markAllRead({ count: 1, items: null });                       // read on the ordinary session
    const named = { count: 1, items: [item("a")] };                              // the private session names it
    const next = reconcile(seen, named);
    expect(next.ids).toEqual(["a"]);
    expect(unreadCount(named, next)).toBe(0);
    expect(unreadCount({ count: 2, items: [item("a"), item("b")] }, next)).toBe(1);   // a new one is unread
  });
});
