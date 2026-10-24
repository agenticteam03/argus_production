// ECharts, tree-shaken to what the metric charts use (about half of the full bundle). SVG renderer, as in the
// ui-graphs prototype: crisp lines at any zoom, and no inline script (the CSP stays `default-src 'self'`).
// ECharts' `use` is imported as `register`: ESLint would take it for React's `use` hook.
import { connect as echartsConnect, init as echartsInit, use as register } from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import {
  AriaComponent, AxisPointerComponent, DataZoomInsideComponent, DataZoomSliderComponent, GridComponent,
  MarkAreaComponent, MarkLineComponent, TooltipComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

// Registered on first use, not when this module is imported: package.json declares the app's modules free of side
// effects (so a real build drops the mock code), and a production build then drops a top-level `register(...)`,
// leaving no renderer ("is not a constructor" on every incident page). build.test.js checks it stays.
let registered = false;
const ready = () => {
  if (registered) return;
  register([
    LineChart, ScatterChart, AriaComponent, AxisPointerComponent, DataZoomInsideComponent, DataZoomSliderComponent,
    GridComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent, SVGRenderer,
  ]);
  registered = true;
};

export const init = (...args) => {
  ready();
  return echartsInit(...args);
};

export const connect = (...args) => {
  ready();
  return echartsConnect(...args);
};
