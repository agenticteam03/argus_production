// Single source of truth for the menu and the router. `roles` limits who sees/opens an item.
export const ROLES = { viewer: "Viewer", operator: "Operator", admin: "Admin" };
export const ROLE_INFO = {
  viewer: "Read-only: ask for diagnostics and browse incidents.",
  operator: "Can launch investigations and approve remediations.",
  admin: "Full access: users, token budget and scheduler.",
};

export const routes = [
  { path: "/", label: "Dashboard" },
  { path: "/incidents", label: "Incidents" },
  { path: "/approvals", label: "Approvals", roles: ["admin"] },
  { path: "/agent", label: "Agent" },
  {
    label: "Tools",
    children: [
      { path: "/tools/simulator", label: "Alert Simulator", desc: "Simulate container stress or send a test webhook", roles: ["operator", "admin"] },
      { path: "/tools/runbooks", label: "Runbooks", desc: "Browse remediation guides" },
      { path: "/tools/scheduler", label: "Scheduler", desc: "Edit recurring health checks", roles: ["admin"] },
    ],
  },
];

export const flat = routes.flatMap((r) => r.children ?? [r]);
export const canSee = (item, role) => !item.roles || item.roles.includes(role);
