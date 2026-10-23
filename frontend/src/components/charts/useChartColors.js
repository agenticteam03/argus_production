import { useEffect, useState } from "react";

// The chart colours come from the same tokens as the rest of the UI (index.css), dark or light. ECharts needs plain
// colours it can add alpha to, and the status tokens are oklch(), so each token is painted on a 1×1 canvas and read
// back as #rrggbb. Re-read whenever <html data-theme> changes, so the charts follow the theme toggle.
const TOKENS = {
  accent: "--color-accent", critical: "--color-red-400", warning: "--color-amber-400", ok: "--color-emerald-400",
  muted: "--color-muted", axis: "--color-muted", grid: "--color-line", surface: "--color-card", ink: "--color-ink",
  border: "--color-field-line",
};

// Without a DOM (a server render, a test) there is nothing to read: neutral greys until the browser draws.
const NO_DOM = Object.fromEntries(Object.keys(TOKENS).map((k) => [k, "#888888"]));

function readColors() {
  if (typeof document === "undefined") return NO_DOM;
  const root = document.documentElement;
  const style = getComputedStyle(root);
  const ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  const out = {};
  for (const [name, token] of Object.entries(TOKENS)) {
    const value = style.getPropertyValue(token).trim();
    if (!ctx || !value) { out[name] = value || "#888888"; continue; }
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = "#000";
    ctx.fillStyle = value;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
    out[name] = `#${[r, g, b].map((n) => n.toString(16).padStart(2, "0")).join("")}`;
  }
  return out;
}

export function useChartColors() {
  const [colors, setColors] = useState(readColors);
  useEffect(() => {
    const observer = new MutationObserver(() => setColors(readColors()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return colors;
}
