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

// The header's toggle. Some components animate their colours (Tailwind `transition`) and others do not, so a plain
// attribute change recolours the page piece by piece. While data-theme-switching is on <html>, index.css pauses every
// transition, so everything changes in the same frame; where the browser supports View Transitions (and the user
// has not asked for reduced motion), the old and new pages also cross-fade as one picture.
export function switchTheme(theme, {
  doc = globalThis.document,
  frame = (cb) => globalThis.requestAnimationFrame(cb),
  reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
} = {}) {
  const root = doc?.documentElement;
  if (!root) return;
  const update = () => { root.dataset.themeSwitching = ""; applyTheme(theme, root); };
  const done = () => { delete root.dataset.themeSwitching; };
  if (typeof doc.startViewTransition === "function" && !reducedMotion) {
    doc.startViewTransition(update).finished.finally(done);
  } else {
    update();
    frame(() => frame(done)); // two frames: the new colours are painted before transitions come back
  }
}
