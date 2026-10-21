// Light / dark theme. The choice is remembered in localStorage (wrapped in try/catch: it can be blocked); with no
// saved choice the app opens dark, which is its base design. The theme is the `data-theme` attribute on <html>, which
// the CSS in index.css reads. No inline script is needed, so the CSP stays strict.
export const THEME_KEY = "argus-theme";
const valid = (t) => (t === "light" || t === "dark" ? t : null);

export function readTheme(storage = globalThis.localStorage) {
  try { return valid(storage?.getItem(THEME_KEY)) ?? "dark"; } catch { return "dark"; }
}

export function saveTheme(theme, storage = globalThis.localStorage) {
  try { storage?.setItem(THEME_KEY, theme); } catch { /* blocked storage: the choice just lasts until reload */ }
}

export function applyTheme(theme, root = globalThis.document?.documentElement) {
  if (root) root.dataset.theme = valid(theme) ?? "dark";
}

export const otherTheme = (theme) => (theme === "light" ? "dark" : "light");
