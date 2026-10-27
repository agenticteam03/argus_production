// Single source of truth for the menu and the router. `roles` limits who sees/opens an item.
// The private Actions entry follows /me's approve_action grant. The local preview flag exposes its
// disabled demonstration; the public read/investigate token never grants approval.
export const ROLES = { viewer: "Viewer", operator: "Operator", approver: "Approver" };
export const ROLE_INFO = {
  viewer: "Read-only: browse incidents and their run timelines.",
  operator: "Can start investigations (ACR-0012); evidence appears when the API grants it.",
  approver: "Can start investigations and decide pending approvals; evidence appears when the API grants it.",
};

export const routes = [
  { path: "/", label: "Dashboard" },
  { path: "/incidents", label: "Incidents" },
  { path: "/actions", label: "Actions", roles: ["operator", "approver"], action: "approve_action", preview: true },
  { path: "/agent", label: "Agent" },
  {
    label: "Tools",
    children: [
      { path: "/tools/runbooks", label: "Runbooks", desc: "Browse remediation guides" },
    ],
  },
];

// Routes that exist but are not menu entries.
// /account/security: the second factor (ACR-0018 step 3), linked from the account menu when /me lists the action.
export const subRoutes = [{ path: "/incidents/:id", label: "Incident" }, { path: "/account/security", label: "Security keys" }];

export const flat = routes.flatMap((r) => r.children ?? [r]);
export const canSee = (item, role, actions = []) =>
  (!item.roles || item.roles.includes(role))
  && (!item.action || actions.includes(item.action)
    || (item.preview && import.meta.env.VITE_ARGUS_PHASE19_DEMO === "1"));
