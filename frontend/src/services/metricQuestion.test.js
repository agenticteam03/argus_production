import { describe, expect, it } from "vitest";
import { answerMetricQuestion, parseInvestigationRequest, parseMetricQuestion } from "./metricQuestion.js";

const rows = [
  { host: "vm-095", available: true, observed_at: "2026-10-14T12:00:00Z",
    values: { cpu_busy_ratio: 0.25, memory_used_ratio: 0.4, disk_used_ratio: 0.7 } },
  { host: "vm-166", available: true, observed_at: "2026-10-14T12:00:00Z",
    values: { cpu_busy_ratio: 0.8, memory_used_ratio: 0.6, disk_used_ratio: 0.9 } },
];

describe("bounded host metric questions", () => {
  it("understands the suggested Host T memory question", () => {
    expect(parseMetricQuestion("Check Host T memory usage")).toEqual({ host: "vm-166", metric: "memory_used_ratio", label: "memory usage" });
    expect(answerMetricQuestion("Check Host T memory usage", rows)).toContain("60.0%");
  });

  it("accepts host A and other named signals, but no ambiguous metric or host", () => {
    expect(parseMetricQuestion("show vm-095 CPU usage")?.metric).toBe("cpu_busy_ratio");
    expect(parseMetricQuestion("Host A disk usage")?.host).toBe("vm-095");
    expect(parseMetricQuestion("Host T CPU and memory")).toBeNull();
    expect(parseMetricQuestion("Host A and Host T memory")).toBeNull();
    expect(parseMetricQuestion("run a command on Host T")).toBeNull();
  });

  it("says when a reading is unavailable instead of inventing a number", () => {
    const unavailable = [{ ...rows[1], available: false, values: { ...rows[1].values, memory_used_ratio: null } }];
    expect(answerMetricQuestion("Check Host T memory usage", unavailable)).toMatch(/No current memory usage data/);
  });

  it("maps a host diagnosis to an inventory target but never treats it as a metric read", () => {
    expect(parseInvestigationRequest("Investigate Host T")).toEqual({ target: "vm-166/host:vm-166", label: "Host T" });
    expect(parseMetricQuestion("Diagnose Host T memory usage")).toBeNull();
    expect(parseInvestigationRequest("Investigate Host A and Host T")).toBeNull();
    expect(parseInvestigationRequest("Don't investigate Host T")).toBeNull();
  });
});
