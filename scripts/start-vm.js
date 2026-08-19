/**
 * VM startup runner: starts backend + frontend only (no install/bootstrap).
 * Intended for VM app server use where dependencies are already present.
 *
 * Usage: npm run start:vm | node start-vm.js | node scripts/start-vm.js
 * Env:   VM_HOST=192.168.1.60
 *        API_PORT=8000 FRONTEND_PORT=5173
 *        API_BIND_HOST=0.0.0.0 FRONTEND_BIND_HOST=0.0.0.0
 *        START_CELERY=1 SKIP_OPEN_BROWSER=1
 *        VITE_API_URL=/api
 *        VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000
 */

const { spawn, execSync } = require("child_process");
const http = require("http");
const net = require("net");
const fs = require("fs");
const path = require("path");

function resolveRepoRoot(fromDir) {
  for (const dir of [fromDir, path.resolve(fromDir, "..")]) {
    if (fs.existsSync(path.join(dir, "backend")) && fs.existsSync(path.join(dir, "frontend"))) {
      return dir;
    }
  }
  throw new Error(
    `Expected backend/ and frontend/ next to the repo root (looked from ${fromDir}). ` +
      "Run from the repository root via `npm run start:vm` or `node start-vm.js`."
  );
}

const ROOT = resolveRepoRoot(__dirname);
const BACKEND = path.join(ROOT, "backend");
const FRONTEND = path.join(ROOT, "frontend");
const children = [];
const isWin = process.platform === "win32";

const VM_HOST = process.env.VM_HOST || "192.168.1.60";
const API_PORT = process.env.API_PORT || "8000";
const FRONTEND_PORT = process.env.FRONTEND_PORT || "5173";
const API_BIND_HOST = process.env.API_BIND_HOST || "0.0.0.0";
const FRONTEND_BIND_HOST = process.env.FRONTEND_BIND_HOST || "0.0.0.0";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function log(msg) {
  console.log(`\x1b[36m[start-vm]\x1b[0m ${msg}`);
}

function warn(msg) {
  console.warn(`\x1b[33m[start-vm]\x1b[0m ${msg}`);
}

function run(cmd, args, opts = {}) {
  const r = spawn(cmd, args, {
    cwd: opts.cwd ?? ROOT,
    stdio: "inherit",
    shell: opts.shell ?? false,
    env: { ...process.env, ...opts.env },
  });
  children.push(r);
  r.on("error", (err) => console.error(`[start-vm] spawn error (${cmd}):`, err.message));
  return r;
}

function runNpm(args, opts = {}) {
  if (isWin) {
    return run("cmd.exe", ["/d", "/s", "/c", "npm", ...args], {
      ...opts,
      shell: false,
    });
  }
  return run("npm", args, { ...opts, shell: false });
}

function hasViteBinary() {
  const candidates = [
    path.join(ROOT, "node_modules", ".bin", "vite.cmd"),
    path.join(ROOT, "node_modules", ".bin", "vite"),
    path.join(FRONTEND, "node_modules", ".bin", "vite.cmd"),
    path.join(FRONTEND, "node_modules", ".bin", "vite"),
  ];
  return candidates.some((p) => fs.existsSync(p));
}

function ensureBackendEnv() {
  const envPath = path.join(BACKEND, ".env");
  const example = path.join(BACKEND, ".env.example");
  if (!fs.existsSync(envPath) && fs.existsSync(example)) {
    fs.copyFileSync(example, envPath);
    log("Created backend/.env from .env.example; set real database and device values before continuing.");
  }
}

function ensureFrontendEnv() {
  const envPath = path.join(FRONTEND, ".env");
  const example = path.join(FRONTEND, ".env.example");
  if (!fs.existsSync(envPath) && fs.existsSync(example)) {
    fs.copyFileSync(example, envPath);
    log("Created frontend/.env from .env.example (VITE_API_URL=/api via Vite proxy).");
  }
}

function venvPythonPath(venvDir) {
  return path.join(
    venvDir,
    isWin ? "Scripts" : "bin",
    isWin ? "python.exe" : "python"
  );
}

function resolveBackendPython() {
  const override = process.env.BACKEND_VENV_PY;
  if (override && fs.existsSync(override)) return override;

  const candidates = [
    venvPythonPath(path.join(BACKEND, ".venv")),
    venvPythonPath(path.join(BACKEND, "venv")),
    venvPythonPath(path.join(BACKEND, "env")),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }

  return null;
}

function envForBackendChild(extra = {}) {
  const e = { ...process.env, PYTHONPATH: BACKEND, ...extra };
  delete e.DATABASE_URL;
  delete e.REDIS_URL;
  return e;
}

function httpOk(urlString, timeoutMs = 3000) {
  return new Promise((resolve) => {
    try {
      const u = new URL(urlString);
      const req = http.request(
        {
          hostname: u.hostname,
          port: u.port || 80,
          path: u.pathname + u.search,
          method: "GET",
          timeout: timeoutMs,
          headers: { Connection: "close", Accept: "*/*" },
        },
        (res) => {
          res.resume();
          resolve(res.statusCode >= 200 && res.statusCode < 400);
        }
      );
      req.on("error", () => resolve(false));
      req.on("timeout", () => {
        req.destroy();
        resolve(false);
      });
      req.end();
    } catch {
      resolve(false);
    }
  });
}

async function waitForHttp(url, label, { maxWaitMs = 120000, intervalMs = 500 } = {}) {
  const start = Date.now();
  let attempt = 0;
  while (Date.now() - start < maxWaitMs) {
    attempt += 1;
    if (await httpOk(url, 3500)) {
      log(`${label} ready (${url})`);
      return;
    }
    if (attempt === 1) log(`Waiting for ${label} at ${url} ...`);
    await sleep(intervalMs);
  }
  throw new Error(`${label} did not respond in time (${url}). Check logs above for errors.`);
}

function openBrowser(url) {
  const explicitOpen = process.env.OPEN_BROWSER === "1";
  const explicitSkip = process.env.SKIP_OPEN_BROWSER === "1";
  if (!explicitOpen || explicitSkip) {
    log("Browser auto-open is disabled for VM mode (set OPEN_BROWSER=1 to enable).");
    return;
  }

  log(`Opening browser: ${url}`);
  try {
    let p = null;
    if (isWin) {
      p = spawn("cmd.exe", ["/d", "/c", "start", "", url], {
        detached: true,
        stdio: "ignore",
        shell: false,
      });
    } else if (process.platform === "darwin") {
      p = spawn("open", [url], { detached: true, stdio: "ignore" });
    } else {
      p = spawn("xdg-open", [url], { detached: true, stdio: "ignore" });
    }

    if (p) {
      p.on("error", (err) => {
        warn(`Could not auto-open browser (${err.message}). Open manually: ${url}`);
      });
      p.unref();
    }
  } catch (e) {
    warn(`Could not open browser (${e.message}). Open manually: ${url}`);
  }
}

function isPortInUse(host, port, timeoutMs = 800) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => {
      resolve(false);
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.connect(port, host);
  });
}

async function preflightChecks() {
  const backendPy = resolveBackendPython();
  if (!backendPy) {
    throw new Error(
      "Missing backend venv python. Expected one of backend/.venv, backend/venv, backend/env (or set BACKEND_VENV_PY). This script does not install dependencies."
    );
  }
  if (!hasViteBinary()) {
    throw new Error("Frontend dependencies are missing (vite). Run `npm install` at the repository root.");
  }
  if (await isPortInUse("127.0.0.1", Number(API_PORT))) {
    throw new Error(
      `API port ${API_PORT} is already in use. Stop existing backend process before running start-vm.js.`
    );
  }
  if (await isPortInUse("127.0.0.1", Number(FRONTEND_PORT))) {
    throw new Error(
      `Frontend port ${FRONTEND_PORT} is already in use. Stop existing Vite process before running start-vm.js.`
    );
  }
  return backendPy;
}

function shutdown() {
  log("Shutting down...");
  for (const c of children) {
    try {
      if (!c.killed && c.pid) {
        if (isWin) {
          execSync(`taskkill /pid ${c.pid} /T /F`, { stdio: "ignore", shell: true });
        } else {
          c.kill("SIGTERM");
        }
      }
    } catch {
      /* ignore */
    }
  }
  process.exit(0);
}

async function main() {
  log(`Biometric attendance VM runner (${VM_HOST})`);
  process.chdir(ROOT);

  if (!fs.existsSync(BACKEND) || !fs.existsSync(FRONTEND)) {
    throw new Error(`Expected backend/ and frontend/ at repository root (${ROOT})`);
  }

  ensureBackendEnv();
  ensureFrontendEnv();
  const backendPython = await preflightChecks();

  log("Applying database migrations (alembic upgrade head)...");
  try {
    execSync(`"${backendPython}" -m alembic upgrade head`, {
      cwd: BACKEND,
      stdio: "inherit",
      env: envForBackendChild(),
    });
  } catch (err) {
    throw new Error(`alembic upgrade head failed: ${err.message}`);
  }

  const envPath = path.join(BACKEND, ".env");
  if (fs.existsSync(envPath)) {
    const raw = fs.readFileSync(envPath, "utf8");
    if (/YOUR_PASSWORD|CHANGE_ME/i.test(raw)) {
      warn("backend/.env still contains placeholder credentials; update DATABASE_URL or DB_* values.");
    }
  }

  const apiUrl = process.env.VITE_API_URL || "/api";
  const devProxyTarget = process.env.VITE_DEV_PROXY_TARGET || `http://127.0.0.1:${API_PORT}`;
  const apiHealthLocal = `http://127.0.0.1:${API_PORT}/health`;
  const frontendPublicOrigin = `http://${VM_HOST}:${FRONTEND_PORT}`;
  const frontendLocalOrigin = `http://127.0.0.1:${FRONTEND_PORT}`;
  const frontendEnv = { ...process.env, VITE_API_URL: apiUrl, VITE_DEV_PROXY_TARGET: devProxyTarget };
  const backendCorsOrigins =
    process.env.CORS_ALLOW_ORIGINS ||
    [
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "http://frontend:5173",
      `http://${VM_HOST}`,
      frontendPublicOrigin,
      frontendLocalOrigin,
    ].join(",");
  const backendEnv = envForBackendChild({ CORS_ALLOW_ORIGINS: backendCorsOrigins });

  log(`Starting FastAPI (uvicorn) on http://${API_BIND_HOST}:${API_PORT} ...`);
  run(
    backendPython,
    ["-m", "uvicorn", "app.main:app", "--reload", "--host", API_BIND_HOST, "--port", API_PORT],
    {
      cwd: BACKEND,
      shell: false,
      env: backendEnv,
    }
  );

  await waitForHttp(apiHealthLocal, "API");

  const startCelery =
    process.env.START_CELERY === "1" ||
    (process.env.START_CELERY !== "0" && process.env.DEVICE_AUTO_SYNC_ENABLED !== "false");
  if (startCelery) {
    log("Starting Celery worker + beat (device auto-sync; needs Redis on REDIS_URL)...");
    run(backendPython, ["-m", "celery", "-A", "app.workers.celery_app", "worker", "-l", "info", "-Q", "attendance_sync,device_commands,reconciliation,notifications"], {
      cwd: BACKEND,
      shell: false,
      env: backendEnv,
    });
    run(backendPython, ["-m", "celery", "-A", "app.workers.celery_app", "beat", "-l", "info"], {
      cwd: BACKEND,
      shell: false,
      env: backendEnv,
    });
  } else {
    log("Celery skipped (START_CELERY=0). Manual Sync still works from the UI.");
  }

  log(
    `Starting Vite on http://${FRONTEND_BIND_HOST}:${FRONTEND_PORT} (API base ${apiUrl}, dev proxy ${devProxyTarget})...`
  );
  runNpm(["run", "dev", "--", "--host", FRONTEND_BIND_HOST, "--port", FRONTEND_PORT, "--strictPort"], {
    cwd: FRONTEND,
    env: frontendEnv,
  });

  await waitForHttp(frontendLocalOrigin + "/", "Frontend");

  log("Startup complete. Ctrl+C stops all processes");
  log(`Frontend (VM): ${frontendPublicOrigin}`);
  log(`API (VM): ${apiUrl} via frontend proxy target ${devProxyTarget}`);
  openBrowser(frontendPublicOrigin + "/");

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  await new Promise(() => {});
}

main().catch((err) => {
  console.error("[start-vm] Fatal:", err.message);
  process.exit(1);
});
