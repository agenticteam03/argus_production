// Single source of truth for the menu and the router. `roles` limits who sees/opens an item.
// Actions is an approver's entry (ACR-0032): the screen leads through the private login and the security key; the
// decisions appear only when /me lists approve_action. The local preview flag fills it with a synthetic approval.
export const ROLES = { viewer: "Viewer", operator: "Operator", approver: "Approver" };
export const ROLE_INFO = {
  viewer: "Read-only: browse incidents and their run timelines.",
  operator: "Can start investigations (ACR-0012); evidence appears when the API grants it.",
  approver: "Can start investigations and decide pending approvals; evidence appears when the API grants it.",
};

export const routes = [
  { path: "/", label: "Dashboard" },
  { path: "/incidents", label: "Incidents" },
  { path: "/actions", label: "Actions", roles: ["approver"] },
  { path: "/agent", label: "Agent" },
  {
    label: "Tools",
    children: [
      { path: "/tools/runbooks", label: "Runbooks", desc: "Browse remediation guides" },
      // ACR-0034/ACR-0040: an approver's or administrator's; the screen leads through the private login and the
      // security key, like Actions, and shows decisions only when /me lists manage_corpus
      { path: "/tools/reference-sources", label: "Reference sources", desc: "Vendor documentation Argus may cite",
        roles: ["approver", "admin"] },
    ],
  },
];

// Routes that exist but are not menu entries.
// /account/security: the second factor (ACR-0018 step 3), linked from the account menu when /me lists the action.
export const subRoutes = [{ path: "/incidents/:id", label: "Incident" }, { path: "/account/security", label: "Security keys" }];

export const flat = routes.flatMap((r) => r.children ?? [r]);
// The roles always apply, the local demo included (T-0016: a viewer saw Actions with VITE_ARGUS_PHASE19_DEMO=1).
export const canSee = (item, role, actions = []) =>
  (!item.roles || item.roles.includes(role)) && (!item.action || actions.includes(item.action));
