// Edge routing for the system map, for the few links ELK does not lay out itself (between hosts, and between the
// active and idle sections of one host). Pure geometry, ported from the ui-graphs prototype (routeBetween,
// placeEdgeLabel, roundedPath). Boxes are {x, y, width, height}; points are {x, y}.

// The router runs a shortest path over a grid built from every box's edges: O(grid²). Fine at the lab's ~15 boxes;
// past this many it draws a plain elbow instead, so a large inventory cannot freeze the page.
export const MAX_ROUTED_NODES = 60;
const GAP = 16;     // the lane kept free around each box
const PAD = 4;      // a route never passes this close to a box

const elbow = (start, end) => {
  const midX = (start.x + end.x) / 2;
  return [start, { x: midX, y: start.y }, { x: midX, y: end.y }, end];
};

// From the source's right side to the target's left side, through free orthogonal lanes around the boxes.
export function routeBetween(source, target, nodes, width, height) {
  const start = { x: source.x + source.width, y: source.y + source.height / 2 };
  const end = { x: target.x, y: target.y + target.height / 2 };
  if (nodes.length > MAX_ROUTED_NODES) return elbow(start, end);
  const a = { x: start.x + 14, y: start.y }, b = { x: end.x - 14, y: end.y };
  const xs = [...new Set([8, width + 8, a.x, b.x, ...nodes.flatMap((n) => [n.x - GAP, n.x + n.width + GAP])])].sort((p, q) => p - q);
  const ys = [...new Set([8, height + 8, a.y, b.y, ...nodes.flatMap((n) => [n.y - GAP, n.y + n.height + GAP])])].sort((p, q) => p - q);
  const inside = (x, y) => nodes.some((n) => x > n.x - PAD && x < n.x + n.width + PAD && y > n.y - PAD && y < n.y + n.height + PAD);
  const blocked = (p, q) => nodes.some((n) => Math.min(p.x, q.x) < n.x + n.width + PAD && Math.max(p.x, q.x) > n.x - PAD
    && Math.min(p.y, q.y) < n.y + n.height + PAD && Math.max(p.y, q.y) > n.y - PAD);
  const nx = xs.length, ny = ys.length, key = (ix, iy) => iy * nx + ix;
  const startKey = key(xs.indexOf(a.x), ys.indexOf(a.y)), endKey = key(xs.indexOf(b.x), ys.indexOf(b.y));
  const dist = new Map([[startKey, 0]]), prev = new Map(), queue = [startKey], visited = new Set();
  while (queue.length) {
    queue.sort((p, q) => dist.get(p) - dist.get(q));
    const k = queue.shift();
    if (visited.has(k)) continue;
    visited.add(k);
    if (k === endKey) break;
    const ix = k % nx, iy = Math.floor(k / nx), p = { x: xs[ix], y: ys[iy] };
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const jx = ix + dx, jy = iy + dy;
      if (jx < 0 || jy < 0 || jx >= nx || jy >= ny) continue;
      const q = { x: xs[jx], y: ys[jy] }, id = key(jx, jy);
      if (inside(q.x, q.y) || blocked(p, q)) continue;
      const cost = dist.get(k) + Math.abs(p.x - q.x) + Math.abs(p.y - q.y) + 1;   // +1 per step: fewer corners win
      if (cost < (dist.get(id) ?? Infinity)) { dist.set(id, cost); prev.set(id, k); queue.push(id); }
    }
  }
  if (!dist.has(endKey)) return elbow(start, end);
  const path = [];
  for (let k = endKey; k !== undefined; k = prev.get(k)) path.unshift({ x: xs[k % nx], y: ys[Math.floor(k / nx)] });
  const full = [start, ...path, end];
  // Drop the points in the middle of a straight run.
  return full.filter((p, i) => i === 0 || i === full.length - 1
    || !((full[i - 1].x === p.x && p.x === full[i + 1].x) || (full[i - 1].y === p.y && p.y === full[i + 1].y)));
}

// A label rectangle beside the route's longest free segment, over no box and no other label.
export function placeEdgeLabel(route, width, height, nodes, labels) {
  const overlaps = (r) => [...nodes, ...labels].some((n) => r.x < n.x + n.width + 5 && r.x + r.width > n.x - 5 && r.y < n.y + n.height + 5 && r.y + r.height > n.y - 5);
  const segments = route.slice(1).map((q, i) => ({ p: route[i], q, length: Math.abs(q.x - route[i].x) + Math.abs(q.y - route[i].y) })).sort((s, t) => t.length - s.length);
  for (const { p, q } of segments) {
    for (const fraction of [0.5, 0.25, 0.75]) {
      for (const side of [1, -1]) {
        const x = p.x + (q.x - p.x) * fraction, y = p.y + (q.y - p.y) * fraction;
        const r = p.y === q.y
          ? { x: x - width / 2, y: y + side * (height / 2 + 6) - height / 2, width, height }
          : { x: x + side * (width / 2 + 8) - width / 2, y: y - height / 2, width, height };
        if (r.x > 0 && r.y > 0 && !overlaps(r)) return r;
      }
    }
  }
  return { x: Math.max(...nodes.map((n) => n.x + n.width)) + 25, y: Math.max(10, ...labels.map((l) => l.y + l.height)) + 10, width, height };
}

// SVG path for an orthogonal route with rounded corners (the geometry stays orthogonal; only the drawing rounds).
export function roundedPath(points, radius = 12) {
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const p = points[i - 1], c = points[i], n = points[i + 1];
    const l1 = Math.hypot(c.x - p.x, c.y - p.y), l2 = Math.hypot(n.x - c.x, n.y - c.y), k = Math.min(radius, l1 / 2, l2 / 2);
    if (!k) { d += ` L${c.x},${c.y}`; continue; }
    d += ` L${c.x + ((p.x - c.x) * k) / l1},${c.y + ((p.y - c.y) * k) / l1} Q${c.x},${c.y} ${c.x + ((n.x - c.x) * k) / l2},${c.y + ((n.y - c.y) * k) / l2}`;
  }
  const e = points.at(-1);
  return `${d} L${e.x},${e.y}`;
}
