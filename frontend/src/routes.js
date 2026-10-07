// Single source of truth for the menu and the router. `action` hides an item unless GET /api/v1/me lists it:
// the server decides what a user may see, the UI never derives permissions from the role (ACR-0001).
// Read-only in this release: no page starts an investigation or answers an approval (that needs a new ACR).
export const ROLES = { viewer: "Viewer", operator: "Operator", approver: "Approver" };
export const ROLE_INFO = {
  viewer: "Reads incidents and their timelines.",
  operator: "Reads incidents, timelines and evidence.",
  approver: "Reads incidents, timelines and evidence.",
};

export const routes = [
  { path: "/", label: "Dashboard" },
  { path: "/incidents", label: "Incidents", action: "view_incidents" },
  {
    label: "Tools",
    children: [
      { path: "/tools/runbooks", label: "Runbooks", desc: "Browse remediation guides" },
    ],
  },
];

export const flat = routes.flatMap((r) => r.children ?? [r]);
export const canSee = (item, user) => !item.action || user.actions.includes(item.action);
