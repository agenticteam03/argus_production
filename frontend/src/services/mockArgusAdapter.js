// Placeholder for the Argus API. Swap for an HTTP adapter with the same method: GET /api/v1/incidents.
// Read-only (ACR-0001): no method starts an investigation or answers an approval. Empty until then.
export const mockArgusAdapter = {
  async getOverview() {
    return {
      incidents: [], // { id, target, title, status, trigger: "alert|scheduled|manual", severity, createdAt }
    };
  },
};
