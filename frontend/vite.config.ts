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
  const apiProxy = {
    "/api": {
      target: devProxyTarget,
      changeOrigin: true,
      // Pass the browser's IP through so per-client rate limits do not lump every user together.
      xfwd: true,
      timeout: PROXY_TIMEOUT_MS,
      proxyTimeout: PROXY_TIMEOUT_MS,
      rewrite: (incomingPath: string) => incomingPath.replace(/^\/api/, ""),
    },
  };

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
      proxy: apiProxy,
    },
    preview: {
      host: "0.0.0.0",
      port: 5173,
      proxy: apiProxy,
    },
    build: {
      target: "es2020",
      // Skipping gzip-size reporting shaves time off builds on the VM.
      reportCompressedSize: false,
      // Export libraries (exceljs, jspdf, docx) are lazy chunks that are large by nature.
      chunkSizeWarningLimit: 1500,
      rollupOptions: {
        output: {
          // React core changes rarely; a separate chunk stays cached across app releases.
          manualChunks(id: string) {
            if (/[\\/]node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom|@remix-run)[\\/]/.test(id)) {
              return "react-vendor";
            }
            return undefined;
          },
        },
      },
    },
  };
});
