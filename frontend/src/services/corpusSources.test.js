import { describe, expect, it, vi } from "vitest";
import { canManageCorpus, corpusObject, decideCorpusSource } from "./corpusSources.js";
import { httpArgusAdapter } from "./httpArgusAdapter.js";
import { mockArgusAdapter } from "./mockArgusAdapter.js";

const staged = { name: "redis", status: "staged", sha256: "b".repeat(64) };

describe("decideCorpusSource", () => {
  it("approves with a step-up bound to the staged bundle, then the POST", async () => {
    const events = [];
    const secondFactor = { stepUp: vi.fn(async () => { events.push("step-up"); return { token: "once" }; }) };
    const argus = { approveCorpusSource: vi.fn(async () => { events.push("post"); return { status: "installed" }; }) };
    expect(await decideCorpusSource({ source: staged, decision: "approve", secondFactor, argus })).toEqual({ status: "installed" });
    expect(secondFactor.stepUp).toHaveBeenCalledWith(`corpus:redis:${"b".repeat(64)}`);
    expect(argus.approveCorpusSource).toHaveBeenCalledWith("redis", { stepUpToken: "once" });
    expect(events).toEqual(["step-up", "post"]);
  });

  it("rejects only with a reason, before asking for the key", async () => {
    const secondFactor = { stepUp: vi.fn(async () => ({ token: "once" })) };
    const argus = { rejectCorpusSource: vi.fn(async () => ({ status: "rejected" })) };
    await expect(decideCorpusSource({ source: staged, decision: "reject", reason: "  ", secondFactor, argus }))
      .rejects.toThrow("needs a reason");
    expect(secondFactor.stepUp).not.toHaveBeenCalled();
    await decideCorpusSource({ source: staged, decision: "reject", reason: " not ours ", secondFactor, argus });
    expect(argus.rejectCorpusSource).toHaveBeenCalledWith("redis", { reason: "not ours", stepUpToken: "once" });
  });

  it("refuses a source that is not staged, and passes a 409 through", async () => {
    const secondFactor = { stepUp: vi.fn(async () => ({ token: "once" })) };
    await expect(decideCorpusSource({ source: { ...staged, status: "installed" }, decision: "approve", secondFactor, argus: {} }))
      .rejects.toThrow("Only a staged source");
    const conflict = Object.assign(new Error("hash mismatch"), { status: 409 });
    const argus = { approveCorpusSource: vi.fn(async () => { throw conflict; }) };
    await expect(decideCorpusSource({ source: staged, decision: "approve", secondFactor, argus })).rejects.toBe(conflict);
  });

  it("names the step-up object and reads the grant from /me", () => {
    expect(corpusObject(staged)).toBe(`corpus:redis:${"b".repeat(64)}`);
    expect(canManageCorpus({ access: "ops", actions: ["manage_corpus"] })).toBe(true);
    expect(canManageCorpus({ access: "read", actions: ["manage_corpus"] })).toBe(false);
    expect(canManageCorpus({ access: "ops", actions: [] })).toBe(false);
  });
});

describe("the adapters", () => {
  it("call the T-0057 routes with the step-up token", async () => {
    const calls = [];
    vi.stubGlobal("fetch", vi.fn(async (url, init = {}) => {
      calls.push([init.method ?? "GET", url, init.body]);
      return { ok: true, status: 200, json: async () => ({}) };
    }));
    await httpArgusAdapter.listCorpusSources();
    await httpArgusAdapter.approveCorpusSource("redis", { stepUpToken: "t1" });
    await httpArgusAdapter.rejectCorpusSource("redis", { reason: "no", stepUpToken: "t2" });
    vi.unstubAllGlobals();
    expect(calls.map(([m, u]) => `${m} ${u}`)).toEqual(["GET /api/v1/ops/corpus/sources",
      "POST /api/v1/ops/corpus/sources/redis/approve", "POST /api/v1/ops/corpus/sources/redis/reject"]);
    expect(JSON.parse(calls[2][2])).toEqual({ reason: "no", step_up_token: "t2" });
  });

  it("the local preview lists one installed and one staged source and installs nothing", async () => {
    const list = await mockArgusAdapter.listCorpusSources();
    expect(list.map((s) => s.status)).toEqual(["installed", "staged"]);
    await expect(mockArgusAdapter.approveCorpusSource("redis", {})).rejects.toMatchObject({ status: 403 });
    await expect(mockArgusAdapter.rejectCorpusSource("redis", {})).rejects.toMatchObject({ status: 403 });
  });
});
