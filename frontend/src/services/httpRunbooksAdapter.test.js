import { afterEach, describe, expect, it, vi } from "vitest";
import { httpRunbooksAdapter } from "./httpRunbooksAdapter.js";
import { clearToken, setToken } from "./session.js";

// ACR-0011 §3.1 row 9 (T-0016 step 4b): in real mode the runbooks are not in the bundle. The edge serves them under
// /runbooks/ only to a request whose bearer token passes GET /api/v1/me, so the UI loads them after login.
const answer = (status, body, text = false) => ({
  ok: status < 400, status,
  json: async () => body,
  text: async () => (text ? body : JSON.stringify(body)),
});

describe("httpRunbooksAdapter", () => {
  afterEach(() => { vi.unstubAllGlobals(); clearToken(); });

  it("loads the index, then each runbook, with the bearer token", async () => {
    setToken("tok");
    const fetch = vi.fn(async (url) => (url === "/runbooks/index.json"
      ? answer(200, ["RB-001-a.md", "RB-002-b.md"])
      : answer(200, `# ${url.split("/").pop()}`, true)));
    vi.stubGlobal("fetch", fetch);
    const list = await httpRunbooksAdapter.listRunbooks();
    expect(list).toEqual([{ file: "RB-001-a.md", markdown: "# RB-001-a.md" }, { file: "RB-002-b.md", markdown: "# RB-002-b.md" }]);
    expect(fetch.mock.calls.map(([u]) => u)).toEqual(["/runbooks/index.json", "/runbooks/RB-001-a.md", "/runbooks/RB-002-b.md"]);
    expect(fetch.mock.calls.every(([, init]) => init.headers.Authorization === "Bearer tok")).toBe(true);
  });

  it("asks only for runbook file names from the index (no path tricks)", async () => {
    setToken("tok");
    const fetch = vi.fn(async (url) => (url === "/runbooks/index.json"
      ? answer(200, ["RB-001-a.md", "../secrets.md", "/etc/passwd", "notes.txt"])
      : answer(200, "# x", true)));
    vi.stubGlobal("fetch", fetch);
    const list = await httpRunbooksAdapter.listRunbooks();
    expect(list.map((r) => r.file)).toEqual(["RB-001-a.md"]);
  });

  it("a 401 ends the session like any API call", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(async () => answer(401, { detail: "expired" })));
    await expect(httpRunbooksAdapter.listRunbooks()).rejects.toMatchObject({ status: 401 });
  });

  it("is loaded once, not polled", () => {
    expect(httpRunbooksAdapter.pollMs).toBe(0);
  });
});
