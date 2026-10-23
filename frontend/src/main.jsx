import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "./index.css";
import App from "./App.jsx";
import { applyTheme, readTheme } from "./utils/theme.js";

applyTheme(readTheme()); // before the first render, so the saved theme is already on <html>

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
