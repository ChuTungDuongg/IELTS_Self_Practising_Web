import { defineConfig } from "@playwright/test";
import { fileURLToPath } from "node:url";
export default defineConfig({
  testDir: ".", testMatch: "*.spec.ts", workers: 1, timeout: 120_000,
  use: { baseURL: "http://127.0.0.1:3107/tests/ux-preview/", channel: "msedge", actionTimeout: 10000, navigationTimeout: 20000 },
  webServer: { cwd: fileURLToPath(new URL("../..", import.meta.url)), command: "node node_modules/vite/bin/vite.js --config tests/ux-preview/vite.config.ts", url: "http://127.0.0.1:3107/tests/ux-preview/", reuseExistingServer: true },
});
