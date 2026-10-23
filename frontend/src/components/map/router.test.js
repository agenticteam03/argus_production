import { describe, expect, it } from "vitest";
import { MAX_ROUTED_NODES, placeEdgeLabel, roundedPath, routeBetween } from "./router.js";

const box = (x, y, width = 100, height = 60) => ({ x, y, width, height });
const PAD = 4;
// Does the segment p→q pass inside a box (grown by PAD)? The router must never do that.
const crosses = (p, q, n) =>
  Math.min(p.x, q.x) < n.x + n.width + PAD && Math.max(p.x, q.x) > n.x - PAD &&
  Math.min(p.y, q.y) < n.y + n.height + PAD && Math.max(p.y, q.y) > n.y - PAD;
const overlap = (a, b) => a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;

describe("routeBetween", () => {
  const source = box(20, 100), target = box(420, 100), wall = box(220, 80, 100, 100);
  const nodes = [source, target, wall];
  const route = routeBetween(source, target, nodes, 600, 300);

  it("starts at the source's right side and ends at the target's left side", () => {
    expect(route[0]).toEqual({ x: 120, y: 130 });
    expect(route.at(-1)).toEqual({ x: 420, y: 130 });
  });

  it("goes around a box in the way, with horizontal and vertical segments only", () => {
    const segments = route.slice(1).map((q, i) => [route[i], q]);
    for (const [p, q] of segments.slice(1, -1)) expect(crosses(p, q, wall)).toBe(false);
    for (const [p, q] of segments) expect(p.x === q.x || p.y === q.y).toBe(true);
  });

  it("falls back to a plain elbow on a very large map instead of searching", () => {
    const many = Array.from({ length: MAX_ROUTED_NODES + 1 }, (_, i) => box(1000 + i * 120, 600));
    const r = routeBetween(source, target, [...nodes, ...many], 2000, 900);
    expect(r[0]).toEqual({ x: 120, y: 130 });
    expect(r.at(-1)).toEqual({ x: 420, y: 130 });
  });
});

describe("placeEdgeLabel", () => {
  it("puts the label beside the route, over no box and no other label", () => {
    const nodes = [box(20, 100), box(420, 100)];
    const route = [{ x: 120, y: 130 }, { x: 420, y: 130 }];
    const other = { x: 220, y: 92, width: 96, height: 40 };
    const r = placeEdgeLabel(route, 96, 40, nodes, [other]);
    for (const n of [...nodes, other]) expect(overlap(r, n)).toBe(false);
    expect(r.width).toBe(96);
  });
});

describe("roundedPath", () => {
  it("keeps the end points and rounds the corners", () => {
    const d = roundedPath([{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 50, y: 40 }]);
    expect(d.startsWith("M0,0")).toBe(true);
    expect(d.endsWith("L50,40")).toBe(true);
    expect(d).toContain("Q50,0");
  });
});
