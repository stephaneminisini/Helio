import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE_URL ?? "http://localhost:8000",
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
