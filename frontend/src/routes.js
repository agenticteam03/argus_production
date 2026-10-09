// Single source of truth for the menu and the router. `roles` limits who sees/opens an item.
// In this release the UI only reads (ACR-0001): write screens (approvals, alert simulator, scheduler) are
// not part of the menu until an ACR gives the UI the matching actions; menu items follow /me actions later.
export const ROLES = { viewer: "Viewer", operator: "Operator", approver: "Approver" };
export const ROLE_INFO = {
  viewer: "Read-only: browse incidents and their run timelines.",
  operator: "Read-only in this release; evidence appears when the API grants it.",
  approver: "Read-only in this release; evidence appears when the API grants it.",
};

export const routes = [
  { path: "/", label: "Dashboard" },
  { path: "/incidents", label: "Incidents" },
  { path: "/agent", label: "Agent" },
  {
    label: "Tools",
    children: [
      { path: "/tools/runbooks", label: "Runbooks", desc: "Browse remediation guides" },
    ],
  },
];

// Routes that exist but are not menu entries.
export const subRoutes = [{ path: "/incidents/:id", label: "Incident" }];

export const flat = routes.flatMap((r) => r.children ?? [r]);
export const canSee = (item, role) => !item.roles || item.roles.includes(role);
