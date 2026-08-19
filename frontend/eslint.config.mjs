import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { react, "react-hooks": reactHooks },
    settings: { react: { version: "detect" } },
    rules: {
      ...react.configs.flat.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // The JSX transform is automatic (tsconfig jsx: react-jsx), so React
      // needs no import and prop types are the job of TypeScript.
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      // A leading underscore marks a parameter kept only to satisfy a
      // signature, which is how the test stubs already spell it.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // Vitest globals are imported explicitly, so only the DOM helpers that
    // jsdom installs need declaring here.
    files: ["**/*.test.{ts,tsx}", "src/test/**/*.ts"],
    languageOptions: { globals: globals.node },
  },
  {
    // The Playwright runner and its config are node code: they read process.env
    // and never run in the browser.
    files: ["e2e/**/*.ts", "playwright.config.ts"],
    languageOptions: { globals: globals.node },
  },
  {
    // The capture script is plain node run from the command line rather than
    // bundled, and no block above matches .mjs, so without this it would be
    // walked and have no rule applied to it at all.
    files: ["scripts/**/*.mjs"],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  }
);
