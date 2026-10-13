// The bearer token lives in memory for the whole tab session — never localStorage, cookies or the URL
// (T-0016 rules). The HTTP adapters read it here; `sessionStore.js` keeps a copy in `sessionStorage` so a reload
// does not log the user out, and AuthContext drops the session when it is cleared.
let token = null;

export const getToken = () => token;
export const setToken = (next) => { token = next ?? null; };
export const clearToken = () => { token = null; };
