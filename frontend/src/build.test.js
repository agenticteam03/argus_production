import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { build } from "vite";
import { afterAll, describe, expect, it } from "vitest";

// ACR-0011 §3.1 row 9 (T-0016 step 4b): a real-mode build ships no mock code, so its demo accounts and fake
// incidents never reach a public bundle. The mock modules are side-effect free (package.json "sideEffects"), so the
// build drops them when VITE_ARGUS_MOCK=0 makes the switch in services/index.js a constant.
const out = mkdtempSync(join(tmpdir(), "argus-ui-real-"));

const bundle = () =>
  readdirSync(join(out, "assets"))
    .filter((f) => f.endsWith(".js"))
    .map((f) => readFileSync(join(out, "assets", f), "utf8"))
    .join("\n");

describe("real-mode build", () => {
  afterAll(() => rmSync(out, { recursive: true, force: true }));

  it("contains no mock adapter, demo password, demo incident or runbook", async () => {
    process.env.VITE_ARGUS_MOCK = "0";
    try {
      await build({ logLevel: "silent", build: { outDir: out, emptyOutDir: true } });
    } finally {
      delete process.env.VITE_ARGUS_MOCK;
    }
    const js = bundle();
    expect(js).toContain("/api/v1/auth/token");          // the real adapter is there
    for (const mock of ["argus-demo", "VITE_ARGUS_USERS", "Demo logins", "inc_7e49840f50fa"]) {
      expect(js).not.toContain(mock);
    }
    // ACR-0011: no runbook text either; the edge serves them after login (/runbooks/, httpRunbooksAdapter)
    expect(js).not.toContain("Container OOM restart loop");
    expect(js).toContain("/runbooks/index.json");
  }, 120_000);
});
