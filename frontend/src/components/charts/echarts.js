// ECharts, tree-shaken to what the metric charts use (about half of the full bundle). SVG renderer, as in the
// ui-graphs prototype: crisp lines at any zoom, and no inline script (the CSP stays `default-src 'self'`).
// ECharts' `use` is imported as `register`: ESLint would take it for React's `use` hook.
import { connect, init, use as register } from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import {
  AriaComponent, AxisPointerComponent, DataZoomInsideComponent, DataZoomSliderComponent, GridComponent,
  MarkAreaComponent, MarkLineComponent, TooltipComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

register([
  LineChart, ScatterChart, AriaComponent, AxisPointerComponent, DataZoomInsideComponent, DataZoomSliderComponent,
  GridComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent, SVGRenderer,
]);

export { connect, init };
