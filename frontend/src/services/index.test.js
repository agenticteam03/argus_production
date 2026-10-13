import { afterEach, describe, expect, it, vi } from "vitest";

// The single swap point: mock adapters by default, the HTTP ones with VITE_ARGUS_MOCK=0.
describe("services index (mock switch)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("defaults to the mock adapters so the offline demo and unit tests work", async () => {
    vi.resetModules();
    const { auth, argus } = await import("./index.js");
    const { mockAuthAdapter } = await import("./mockAuthAdapter.js");
    const { mockArgusAdapter } = await import("./mockArgusAdapter.js");
    expect(auth).toBe(mockAuthAdapter);
    expect(argus).toBe(mockArgusAdapter);
  });

  it("uses the HTTP adapters when VITE_ARGUS_MOCK=0", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_ARGUS_MOCK", "0");
    const { auth, argus } = await import("./index.js");
    const { httpAuthAdapter } = await import("./httpAuthAdapter.js");
    const { httpArgusAdapter } = await import("./httpArgusAdapter.js");
    expect(auth).toBe(httpAuthAdapter);
    expect(argus).toBe(httpArgusAdapter);
  });

  it("reports the data source so the UI can label demo data", async () => {
    vi.resetModules();
    const demo = await import("./index.js");
    expect(demo.dataSource).toBe("demo");

    vi.resetModules();
    vi.stubEnv("VITE_ARGUS_MOCK", "0");
    const real = await import("./index.js");
    expect(real.dataSource).toBe("api");
  });
});
