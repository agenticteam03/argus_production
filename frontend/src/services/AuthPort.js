/**
 * Output port: what the UI needs from any authentication provider.
 * Adapters (mock today, HTTP tomorrow) must implement this shape.
 * The user is GET /api/v1/me for a read token: the UI shows a control only when `actions` lists it.
 *
 * @typedef {Object} AuthPort
 * @property {(credentials: {username: string, password: string}) =>
 *           Promise<{user: {name: string, role: string, access: string, actions: string[]}}>} signIn
 *           Resolves with the session, rejects with an Error whose message is safe to show.
 * @property {() => Promise<void>} signOut
 */
export {};
