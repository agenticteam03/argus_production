import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";

// T-0016 "Lint and build": the recommended JavaScript rules and the React hooks rules, on the app, its unit tests
// and the Playwright acceptance tests.
export default [
  { ignores: ["dist", "dist-e2e", "test-results", "playwright-report"] },
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { react, "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "react/jsx-uses-vars": "error",              // a component used only in JSX is used
      "no-unused-vars": ["error", { ignoreRestSiblings: true, argsIgnorePattern: "^_" }],   // `{ evidence, audit, ...rest }` drops fields
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  // Node-side files: the configs, the build and contract tests, the acceptance tests.
  {
    files: ["*.config.js", "e2e/**/*.js", "src/**/*.test.js"],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
  // Playwright fixtures call `use` too, which is not a React hook.
  { files: ["e2e/**/*.js"], rules: { "react-hooks/rules-of-hooks": "off" } },
];
