import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const root = path.dirname(fileURLToPath(import.meta.url));
const dashboardSrc = path.resolve(root, "../dashboard/src");
const adminClient = path.resolve(root, "src/api/client.ts");
const adminSse = path.resolve(root, "src/hooks/useSSE.ts");

export default defineConfig({
  resolve: {
    dedupe: ["react", "react-dom"],
    alias: [
      { find: "@dashboard", replacement: dashboardSrc },
      {
        find: path.resolve(dashboardSrc, "api/client.ts"),
        replacement: adminClient,
      },
      {
        find: path.resolve(dashboardSrc, "api/client"),
        replacement: adminClient,
      },
      {
        find: path.resolve(dashboardSrc, "hooks/useSSE.ts"),
        replacement: adminSse,
      },
      {
        find: path.resolve(dashboardSrc, "hooks/useSSE"),
        replacement: adminSse,
      },
    ],
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
