import { describe, expect, it } from "vitest";
import { ageLabel, fleetStatus, nodeHealth, nodeIcon, STALE_MS } from "./fleetStatus.js";

const NOW = Date.parse("2026-10-20T15:00:00Z");
const HOSTS = { "vm-095": "Host A", "vm-166": "Host T" };
const sample = (host, values, secondsAgo = 5) => ({ host, available: true, observed_at: new Date(NOW - secondsAgo * 1000).toISOString(), values });
const calm = { cpu_busy_ratio: 0.1, memory_used_ratio: 0.3, disk_used_ratio: 0.4 };
const run = (o) => fleetStatus({ hosts: HOSTS, now: NOW, hostMetrics: [sample("vm-095", calm), sample("vm-166", calm)], ...o });

describe("fleetStatus", () => {
  it("is 'checking' until the first reading arrives", () => {
    expect(run({ loaded: false }).level).toBe("checking");
  });

  it("is good when hosts are calm, fresh, and nothing was escalated", () => {
    const s = run();
    expect(s.level).toBe("good");
    expect(s.headline).toBe("All monitored hosts look healthy");
    expect(s.attention).toEqual([]);
    expect(s.stats.hostsReporting).toBe(2);
  });

  it("warns about a high host and names the worst metric", () => {
    const s = run({ hostMetrics: [sample("vm-095", calm), sample("vm-166", { ...calm, memory_used_ratio: 0.8, disk_used_ratio: 0.77 })] });
    expect(s.level).toBe("warn");
    expect(s.attention[0].text).toBe("Host T (vm-166): Memory high at 80.0%");
  });

  it("is critical when a metric reaches 90 %", () => {
    const s = run({ hostMetrics: [sample("vm-095", { ...calm, disk_used_ratio: 0.93 }), sample("vm-166", calm)] });
    expect(s.level).toBe("critical");
    expect(s.headline).toBe("1 issue needs your attention");
    expect(s.attention[0]).toEqual({ tone: "critical", text: "Host A (vm-095): Disk / critical at 93.0%" });
  });

  it("flags a stale sample and a host with no data, never calling them healthy", () => {
    const stale = run({ hostMetrics: [sample("vm-095", calm, STALE_MS / 1000 + 60), sample("vm-166", calm)] });
    expect(stale.level).toBe("warn");
    expect(stale.hosts[0].reporting).toBe(false);
    expect(stale.attention[0].text).toMatch(/^Host A \(vm-095\): signals are stale/);
    const none = run({ hostMetrics: [sample("vm-166", calm)] });
    expect(none.attention[0].text).toBe("Host A (vm-095): no current metrics");
    expect(none.stats.hostsReporting).toBe(1);
  });

  it("counts recent escalations (24 h) with a link, and running investigations", () => {
    const incidents = [
      { id: "inc_1", target: "vm-166/container:x", status: "escalated", opened_at: new Date(NOW - 3600e3).toISOString() },
      { id: "inc_2", target: "vm-166/container:y", status: "escalated", opened_at: new Date(NOW - 30 * 3600e3).toISOString() },
      { id: "inc_3", target: "vm-095/host:vm-095", status: "running", opened_at: new Date(NOW - 60e3).toISOString() },
    ];
    const s = run({ incidents });
    expect(s.attention).toEqual([{ tone: "warning", text: "Escalated to a person: vm-166/container:x", to: "/incidents/inc_1" }]);
    expect(s.counts.running).toBe(1);
    expect(s.stats.escalated).toBe(1);
  });

  it("uses the topology: a broken link is critical, unknown components are counted, read edges are not links", () => {
    const topology = {
      nodes: [{ id: "a", label: "agent", kind: "argus" }, { id: "c", label: "client", status: "running" }, { id: "b", label: "backend", status: "unknown" }, { id: "d", label: "db" }],
      edges: [{ from: "c", to: "b", state: "broken", label: "connection refused" }, { from: "c", to: "d", state: "ok" }, { from: "a", to: "c", state: "read" }],
    };
    const s = run({ topology });
    expect(s.level).toBe("critical");
    expect(s.attention[0].text).toBe("Dependency broken: client → backend (connection refused)");
    expect(s.stats.links).toEqual({ ok: 1, total: 2 });
    expect(s.stats.components).toEqual({ total: 3, unknown: 2 });
    expect(s.nodes.map((n) => n.health)).toEqual(["failed", "failed", "unknown"]);
  });

  it("has no link or component stats without a topology", () => {
    expect(run().stats.links).toBeNull();
    expect(run().stats.components).toBeNull();
  });
});

describe("nodeHealth / ageLabel", () => {
  it("never draws a missing or unknown status as ok", () => {
    expect(nodeHealth({ id: "x" })).toBe("unknown");
    expect(nodeHealth({ id: "x", status: "unknown" })).toBe("unknown");
    expect(nodeHealth({ id: "x", status: "running" })).toBe("ok");
    expect(nodeHealth({ id: "x", status: "restarting" })).toBe("degraded");
    expect(nodeHealth({ id: "x", status: "running" }, new Set(["x"]))).toBe("failed");
  });
  it("says how old a sample is", () => {
    expect(ageLabel(4000)).toBe("4 s ago");
    expect(ageLabel(3 * 60e3)).toBe("3 min ago");
    expect(ageLabel(2 * 3600e3)).toBe("2 h ago");
    expect(ageLabel(null)).toBeNull();
  });
});

describe("nodeIcon", () => {
  it("picks database, server or container", () => {
    expect(nodeIcon({ id: "x", label: "app-db" })).toBe("database");
    expect(nodeIcon({ id: "x", label: "postgres", kind: "app" })).toBe("database");
    expect(nodeIcon({ id: "vm-166/host:vm-166", label: "vm-166", target: "vm-166/host:vm-166" })).toBe("server");
    expect(nodeIcon({ id: "x", label: "argus-lab-client", kind: "app" })).toBe("box");
  });
  it("is carried on each honeycomb node", () => {
    const topology = { nodes: [{ id: "a", label: "app-db", status: "running" }, { id: "b", label: "client", status: "running" }], edges: [] };
    expect(fleetStatus({ hosts: {}, hostMetrics: [], topology, now: Date.now() }).nodes.map((n) => n.icon)).toEqual(["database", "box"]);
  });
});
