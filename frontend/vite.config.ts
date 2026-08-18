import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // The dev server stands in for the nginx proxy the production image runs,
    // so the app is served from one origin either way. This target is where the
    // API listens on the host, not a URL the browser ever sees.
    proxy: {
      "/api": {
        target: process.env.HELIO_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // The browser smoke tests are also named *.spec.ts, and vitest would pick
    // them up and fail on Playwright's fixtures. They belong to `npm run e2e`.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
