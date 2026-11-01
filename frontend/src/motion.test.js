// T-0016 motion: the contract of src/motion.css, read as text. Every animation is a theme token, moves only what the
// compositor can move (opacity, transform), takes its colours from the colour tokens, and is switched off by
// prefers-reduced-motion: reduce.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./motion.css", import.meta.url), "utf8");
const index = readFileSync(new URL("./index.css", import.meta.url), "utf8");

export const ANIMATIONS = ["shimmer", "rise", "fade-in", "pop", "drop", "page-in", "dialog-in", "slide-in-right", "grow-x", "shake", "ring"];
const DURATIONS = ["--motion-fast", "--motion-base", "--motion-slow", "--motion-count", "--motion-stagger", "--motion-shimmer"];

// The body of the first block opened by `head` (a selector or an at-rule), braces balanced.
function block(text, head) {
  const at = text.indexOf(head);
  if (at < 0) return null;
  let depth = 0;
  const open = text.indexOf("{", at);
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    if (text[i] === "}" && (depth -= 1) === 0) return text.slice(open + 1, i);
  }
  return null;
}
const keyframes = () => [...css.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => [m[1], block(css, m[0])]);
const declared = (body) => [...body.matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]);

describe("motion tokens (src/motion.css)", () => {
  it("is part of the theme stylesheet", () => {
    expect(index).toMatch(/@import\s+["']\.\/motion\.css["']/);
  });

  it("names every animation as an --animate-* theme token, with its keyframes", () => {
    const theme = block(css, "@theme");
    expect(theme).not.toBeNull();
    const names = keyframes().map(([name]) => name);
    for (const name of ANIMATIONS) {
      expect(theme, `--animate-${name}`).toMatch(new RegExp(`--animate-${name}:\\s*${name}\\s`));
      expect(names, `@keyframes ${name}`).toContain(name);
    }
  });

  it("times every animation with the --motion-* durations and the theme's easings", () => {
    const root = block(css, ":root");
    for (const d of DURATIONS) expect(root, d).toMatch(new RegExp(`${d}:\\s*[\\d.]+m?s`));
    expect(block(css, "@theme")).toMatch(/--ease-out-soft:/);
  });

  it("moves only opacity and transform, which the compositor animates without layout or paint", () => {
    for (const [name, body] of keyframes()) {
      for (const prop of declared(body)) expect(["opacity", "transform"], `@keyframes ${name}: ${prop}`).toContain(prop);
    }
  });

  it("uses only the theme's colour tokens, never a literal colour", () => {
    const literal = css.replace(/\/\*[\s\S]*?\*\//g, "").match(/#[0-9a-f]{3,8}\b|\b(rgb|rgba|hsl|hsla|oklch|oklab)\(/gi);
    expect(literal).toBeNull();
    for (const token of ["--color-skeleton", "--color-shimmer", "--color-shadow"]) {
      expect(css).toContain(`var(${token})`);
      expect(index).toMatch(new RegExp(`@theme[\\s\\S]*${token}:`));                 // dark value
      expect(block(index, ':root[data-theme="light"]'), token).toContain(`${token}:`); // light value
    }
  });

  it("turns every animation and duration off for prefers-reduced-motion: reduce", () => {
    const reduce = block(css, "@media (prefers-reduced-motion: reduce)");
    expect(reduce).not.toBeNull();
    for (const name of [...ANIMATIONS, "pulse", "ping", "bounce"]) expect(reduce, name).toMatch(new RegExp(`--animate-${name}:\\s*none`));
    for (const d of DURATIONS) expect(reduce, d).toMatch(new RegExp(`${d}:\\s*0m?s`));
  });

  it("presses buttons and lifts cards only when motion is welcome", () => {
    const welcome = block(css, "@media (prefers-reduced-motion: no-preference)");
    expect(welcome).toMatch(/button:not\(:disabled\):active/);
    expect(block(css, "@utility lift")).toContain("prefers-reduced-motion: no-preference");
  });
});
