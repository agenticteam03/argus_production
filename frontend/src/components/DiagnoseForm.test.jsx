import { describe, expect, it, vi } from "vitest";

vi.mock("../context/AuthContext.jsx", () => ({ useAuth: () => ({ user: null }) }));
vi.mock("../services/index.js", () => ({ argus: {} }));
const { targetOptions } = await import("./DiagnoseForm.jsx");

const rows = [
  { target: "vm-166/container:argus-lab-api", state: "running" },
  { target: "vm-166/container:argus-lab-client", state: "stopped" },
  { target: "vm-166/container:argus-lab-burner", state: "absent" },
  { target: "vm-166/service:cron.service", state: "unknown" },
];

describe("DiagnoseForm target list (ACR-0044)", () => {
  it("hides the targets that are not on their host and marks the stopped ones", () => {
    const { options, hidden } = targetOptions(rows, false);
    expect(options.map((o) => o.label)).toEqual([
      "vm-166/container:argus-lab-api", "vm-166/container:argus-lab-client (stopped)", "vm-166/service:cron.service"]);
    expect(hidden).toBe(1);
  });

  it("shows every inventory target when asked", () => {
    const { options, hidden } = targetOptions(rows, true);
    expect(options).toHaveLength(4);
    expect(options[2]).toEqual({ value: "vm-166/container:argus-lab-burner", label: "vm-166/container:argus-lab-burner (not on its host)" });
    expect(hidden).toBe(0);
  });

  it("keeps a target with no state (an older API) visible", () => {
    expect(targetOptions([{ target: "h/container:x" }], false)).toEqual({ options: [{ value: "h/container:x", label: "h/container:x" }], hidden: 0 });
    expect(targetOptions(null, false)).toEqual({ options: [], hidden: 0 });
  });
});
