import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const root = path.dirname(fileURLToPath(import.meta.url));
const dashboardSrc = path.resolve(root, "../dashboard/src");
const adminClient = path.resolve(root, "src/api/client.ts");
const adminSse = path.resolve(root, "src/hooks/useSSE.ts");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, root, "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8402";

  return {
    plugins: [react()],
    resolve: {
      dedupe: ["react", "react-dom", "@tanstack/react-virtual"],
      alias: [
        {
          find: "@tanstack/react-virtual",
          replacement: path.resolve(root, "node_modules/@tanstack/react-virtual"),
        },
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
    server: {
      host: "127.0.0.1",
      port: 5174,
      strictPort: true,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
