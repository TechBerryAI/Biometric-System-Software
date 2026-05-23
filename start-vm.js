/**
 * VM startup runner: starts backend + frontend only (no install/bootstrap).
 * Intended for VM app server use where dependencies are already present.
 *
 * Usage: node start-vm.js
 * Env:   VM_HOST=192.168.1.117
 *        API_PORT=8000 FRONTEND_PORT=5173
 *        API_BIND_HOST=0.0.0.0 FRONTEND_BIND_HOST=0.0.0.0
 *        START_CELERY=1 SKIP_OPEN_BROWSER=1
 *        VITE_API_URL=http://192.168.1.117:8000
 */

const { spawn, execSync } = require("child_process");
const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname);
const BACKEND = path.join(ROOT, "backend");
const FRONTEND = path.join(ROOT, "frontend");
const children = [];
const isWin = process.platform === "win32";

const VM_HOST = process.env.VM_HOST || "192.168.1.117";
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
  const viteCmd = path.join(FRONTEND, "node_modules", ".bin", "vite.cmd");
  const viteBin = path.join(FRONTEND, "node_modules", ".bin", "vite");
  return fs.existsSync(viteCmd) || fs.existsSync(viteBin);
}

function ensureBackendEnv() {
  const envPath = path.join(BACKEND, ".env");
  const example = path.join(BACKEND, ".env.example");
  if (!fs.existsSync(envPath) && fs.existsSync(example)) {
    fs.copyFileSync(example, envPath);
    log("Created backend/.env from .env.example; set real database and device values before continuing.");
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
  if (process.env.SKIP_OPEN_BROWSER === "1") {
    log("SKIP_OPEN_BROWSER=1 -> not opening browser.");
    return;
  }
  log(`Opening browser: ${url}`);
  try {
    if (isWin) {
      const p = spawn("cmd.exe", ["/d", "/c", "start", "", url], {
        detached: true,
        stdio: "ignore",
        shell: false,
      });
      p.unref();
    } else if (process.platform === "darwin") {
      const p = spawn("open", [url], { detached: true, stdio: "ignore" });
      p.unref();
    } else {
      const p = spawn("xdg-open", [url], { detached: true, stdio: "ignore" });
      p.unref();
    }
  } catch (e) {
    warn(`Could not open browser (${e.message}). Open manually: ${url}`);
  }
}

function preflightChecks() {
  const backendPy = resolveBackendPython();
  if (!backendPy) {
    throw new Error(
      "Missing backend venv python. Expected one of backend/.venv, backend/venv, backend/env (or set BACKEND_VENV_PY). This script does not install dependencies."
    );
  }
  if (!fs.existsSync(path.join(FRONTEND, "node_modules")) || !hasViteBinary()) {
    throw new Error("Frontend dependencies are missing (node_modules/vite). This script does not run npm install.");
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
    throw new Error("Expected backend/ and frontend/ next to start-vm.js");
  }

  ensureBackendEnv();
  const backendPython = preflightChecks();

  const envPath = path.join(BACKEND, ".env");
  if (fs.existsSync(envPath)) {
    const raw = fs.readFileSync(envPath, "utf8");
    if (/YOUR_PASSWORD|CHANGE_ME/i.test(raw)) {
      warn("backend/.env still contains placeholder credentials; update DATABASE_URL or DB_* values.");
    }
  }

  const apiUrl = process.env.VITE_API_URL || `http://${VM_HOST}:${API_PORT}`;
  const apiHealthLocal = `http://127.0.0.1:${API_PORT}/health`;
  const frontendPublicOrigin = `http://${VM_HOST}:${FRONTEND_PORT}`;
  const frontendLocalOrigin = `http://127.0.0.1:${FRONTEND_PORT}`;
  const frontendEnv = { ...process.env, VITE_API_URL: apiUrl };

  log(`Starting FastAPI (uvicorn) on http://${API_BIND_HOST}:${API_PORT} ...`);
  run(
    backendPython,
    ["-m", "uvicorn", "app.main:app", "--reload", "--host", API_BIND_HOST, "--port", API_PORT],
    {
      cwd: BACKEND,
      shell: false,
      env: envForBackendChild(),
    }
  );

  await waitForHttp(apiHealthLocal, "API");

  if (process.env.START_CELERY === "1") {
    log("Starting Celery worker + beat (requires Redis)...");
    run(backendPython, ["-m", "celery", "-A", "app.workers.celery_app", "worker", "-l", "info"], {
      cwd: BACKEND,
      shell: false,
      env: envForBackendChild(),
    });
    run(backendPython, ["-m", "celery", "-A", "app.workers.celery_app", "beat", "-l", "info"], {
      cwd: BACKEND,
      shell: false,
      env: envForBackendChild(),
    });
  } else {
    log("Tip: set START_CELERY=1 to run worker+beat (requires Redis)");
  }

  log(`Starting Vite on http://${FRONTEND_BIND_HOST}:${FRONTEND_PORT} (API ${apiUrl})...`);
  runNpm(["run", "dev", "--", "--host", FRONTEND_BIND_HOST, "--port", FRONTEND_PORT], {
    cwd: FRONTEND,
    env: frontendEnv,
  });

  await waitForHttp(frontendLocalOrigin + "/", "Frontend");

  log("Startup complete. Ctrl+C stops all processes");
  log(`Frontend (VM): ${frontendPublicOrigin}`);
  log(`API (VM): ${apiUrl}`);
  openBrowser(frontendPublicOrigin + "/");

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  await new Promise(() => {});
}

main().catch((err) => {
  console.error("[start-vm] Fatal:", err.message);
  process.exit(1);
});
