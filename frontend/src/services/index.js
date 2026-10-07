// Composition point: swap these adapters for the real HTTP ones when the backend is ready.
export { mockAuthAdapter as auth } from "./mockAuthAdapter.js";
export { mockArgusAdapter as argus } from "./mockArgusAdapter.js";
export { mockRunbooksAdapter as runbooks } from "./mockRunbooksAdapter.js";
