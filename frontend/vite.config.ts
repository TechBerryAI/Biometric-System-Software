import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

/** Match frontend SYNC_HTTP_TIMEOUT_MS — full ZK pulls can take several minutes. */
const PROXY_TIMEOUT_MS = 600_000;

function longRunningApiTimeouts(): Plugin {
  return {
    name: "long-running-api-timeouts",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        req.setTimeout(PROXY_TIMEOUT_MS);
        res.setTimeout(PROXY_TIMEOUT_MS);
        next();
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const devProxyTarget = env.VITE_DEV_PROXY_TARGET || "http://localhost:8000";

  return {
    plugins: [react(), longRunningApiTimeouts()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": {
          target: devProxyTarget,
          changeOrigin: true,
          timeout: PROXY_TIMEOUT_MS,
          proxyTimeout: PROXY_TIMEOUT_MS,
          rewrite: (incomingPath) => incomingPath.replace(/^\/api/, ""),
        },
      },
    },
  };
});
