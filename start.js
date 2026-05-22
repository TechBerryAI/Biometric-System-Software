/**
 * Local dev startup: backend venv + pip, Alembic migrations, frontend npm install, uvicorn + Vite.
 * Requires PostgreSQL (and Redis if you use START_CELERY=1). Configure backend/.env first.
 *
 * Usage: node start.js
 * Env:   PYTHON=path\to\python.exe   START_CELERY=1   SKIP_OPEN_BROWSER=1
 *        FRONTEND_PORT=5173   VITE_API_URL=http://localhost:8000
 */

const { spawn, execSync } = require("child_process");
const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname);
const BACKEND = path.join(ROOT, "backend");
const FRONTEND = path.join(ROOT, "frontend");
const VENV_DIR = path.join(BACKEND, ".venv");
const VENV_PY = path.join(
  VENV_DIR,
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python"
);
const children = [];
const isWin = process.platform === "win32";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function log(msg) {
  console.log(`\x1b[36m[start]\x1b[0m ${msg}`);
}

function warn(msg) {
  console.warn(`\x1b[33m[start]\x1b[0m ${msg}`);
}

function run(cmd, args, opts = {}) {
  const r = spawn(cmd, args, {
    cwd: opts.cwd ?? ROOT,
    stdio: "inherit",
    shell: opts.shell ?? false,
    env: { ...process.env, ...opts.env },
  });
  children.push(r);
  r.on("error", (err) => console.error(`[start] spawn error (${cmd}):`, err.message));
  return r;
}

/** Run npm reliably on Windows without spawn EINVAL / shell deprecation warnings. */
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
    log("Created backend/.env from .env.example ? edit DATABASE_URL (password) before continuing.");
  }
}

function resolvePythonLauncher() {
  if (process.env.PYTHON) return { cmd: process.env.PYTHON, argsPrefix: [] };
  try {
    execSync("python --version", { stdio: "ignore", shell: isWin });
    return { cmd: "python", argsPrefix: [] };
  } catch {
    /* continue */
  }
  try {
    execSync("py -3 --version", { stdio: "ignore", shell: isWin });
    return { cmd: "py", argsPrefix: ["-3"] };
  } catch {
    throw new Error(
      "Python 3.11+ not found. Install Python or set PYTHON to your python.exe path."
    );
  }
}

async function ensureVenv() {
  const forceRecreate = process.env.FORCE_RECREATE_VENV === "1";
  if (forceRecreate && fs.existsSync(VENV_DIR)) {
    log("FORCE_RECREATE_VENV=1 -> removing existing backend/.venv ...");
    fs.rmSync(VENV_DIR, { recursive: true, force: true });
  }

  if (!fs.existsSync(VENV_PY)) {
    log("Creating backend virtualenv...");
    const { cmd, argsPrefix } = resolvePythonLauncher();
    const args = [...argsPrefix, "-m", "venv", ".venv"];
    const r = spawn(cmd, args, { cwd: BACKEND, stdio: "inherit", shell: false });
    const code = await waitForExit(r);
    if (code !== 0) throw new Error(`venv creation failed with exit ${code}`);
  } else {
    log("Backend virtualenv already exists");
  }

  const verify = spawn(VENV_PY, ["-c", "import sys; print(sys.executable)"], {
    cwd: BACKEND,
    stdio: "inherit",
    shell: false,
  });
  const verifyCode = await waitForExit(verify);
  if (verifyCode !== 0) {
    throw new Error("backend/.venv exists but python executable failed. Recreate with FORCE_RECREATE_VENV=1.");
  }
}

function waitForExit(proc) {
  return new Promise((resolve, reject) => {
    proc.on("exit", (code) => resolve(code ?? 0));
    proc.on("error", reject);
  });
}

/** Shell env DATABASE_URL can override backend/.env; drop so pydantic reads the file. */
function envForBackendChild(extra = {}) {
  const e = { ...process.env, PYTHONPATH: BACKEND, ...extra };
  delete e.DATABASE_URL;
  delete e.REDIS_URL;
  return e;
}

/** True if HTTP GET returns 2xx/3xx (server accepting connections). */
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

async function waitForHttp(url, label, { maxWaitMs = 120000, intervalMs = 400 } = {}) {
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
    log("SKIP_OPEN_BROWSER=1 ? not opening a browser tab.");
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

async function pipInstall() {
  if (!fs.existsSync(VENV_PY)) {
    throw new Error("Virtualenv python missing at backend/.venv. Run with FORCE_RECREATE_VENV=1.");
  }
  const requirementsPath = path.join(BACKEND, "requirements.txt");
  if (!fs.existsSync(requirementsPath)) {
    throw new Error(`requirements.txt not found at ${requirementsPath}`);
  }

  log("Installing Python dependencies into backend/.venv ...");

  const upgradePip = spawn(VENV_PY, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], {
    cwd: BACKEND,
    stdio: "inherit",
    shell: false,
  });
  const upgradeCode = await waitForExit(upgradePip);
  if (upgradeCode !== 0) throw new Error(`pip bootstrap failed with exit ${upgradeCode}`);

  const r = spawn(
    VENV_PY,
    ["-m", "pip", "install", "--require-virtualenv", "-r", requirementsPath],
    {
      cwd: BACKEND,
      stdio: "inherit",
      shell: false,
    }
  );
  const code = await waitForExit(r);
  if (code !== 0) throw new Error(`pip install failed with exit ${code}`);

  const freezeCheck = spawn(VENV_PY, ["-m", "pip", "--version"], {
    cwd: BACKEND,
    stdio: "inherit",
    shell: false,
  });
  const freezeCode = await waitForExit(freezeCheck);
  if (freezeCode !== 0) throw new Error(`pip verification failed with exit ${freezeCode}`);
}

async function alembicUpgrade() {
  log("Running database migrations...");
  const py = VENV_PY;
  const r = spawn(py, ["-m", "alembic", "upgrade", "head"], {
    cwd: BACKEND,
    stdio: "inherit",
    shell: false,
    env: envForBackendChild(),
  });
  const code = await waitForExit(r);
  if (code !== 0) {
    warn(
      "Alembic failed ? check PostgreSQL is running, database exists, and DATABASE_URL in backend/.env is correct."
    );
    throw new Error(`alembic upgrade failed with exit ${code}`);
  }
}

async function npmInstallFrontend() {
  const hasNodeModules = fs.existsSync(path.join(FRONTEND, "node_modules"));
  if (hasNodeModules && hasViteBinary()) {
    log("Frontend dependencies present; skipping npm install");
    return;
  }
  if (hasNodeModules && !hasViteBinary()) {
    warn("node_modules exists but vite binary is missing ? reinstalling frontend dependencies");
  } else {
    log("Installing frontend dependencies (npm install)...");
  }
  const r = runNpm(["install"], { cwd: FRONTEND });
  const code = await waitForExit(r);
  if (code !== 0) throw new Error(`npm install failed with exit ${code}`);
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
  log("Biometric attendance ? dev startup (local PostgreSQL)");
  process.chdir(ROOT);

  if (!fs.existsSync(BACKEND) || !fs.existsSync(FRONTEND)) {
    throw new Error("Expected backend/ and frontend/ next to start.js");
  }

  ensureBackendEnv();

  const envPath = path.join(BACKEND, ".env");
  if (fs.existsSync(envPath)) {
    const raw = fs.readFileSync(envPath, "utf8");
    if (/YOUR_PASSWORD|CHANGE_ME/i.test(raw)) {
      warn(
        "backend/.env still contains YOUR_PASSWORD or CHANGE_ME ? set DATABASE_URL to your real PostgreSQL password."
      );
    }
  }

  await ensureVenv();
  await pipInstall();
  await alembicUpgrade();
  await npmInstallFrontend();

  const apiUrl = process.env.VITE_API_URL || "http://localhost:8000";
  const apiHealth = apiUrl.replace(/\/$/, "") + "/health";
  const fePort = process.env.FRONTEND_PORT || "5173";
  const feOrigin = `http://localhost:${fePort}`;
  const feEnv = { ...process.env, VITE_API_URL: apiUrl };

  log("Starting FastAPI (uvicorn) on http://0.0.0.0:8000 ...");
  run(VENV_PY, ["-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"], {
    cwd: BACKEND,
    shell: false,
    env: envForBackendChild(),
  });

  await waitForHttp(apiHealth, "API", { maxWaitMs: 120000, intervalMs: 500 });

  if (process.env.START_CELERY === "1") {
    log("Starting Celery worker + beat (device polling; needs Redis on REDIS_URL)...");
    run(VENV_PY, ["-m", "celery", "-A", "app.workers.celery_app", "worker", "-l", "info"], {
      cwd: BACKEND,
      shell: false,
      env: envForBackendChild(),
    });
    run(VENV_PY, ["-m", "celery", "-A", "app.workers.celery_app", "beat", "-l", "info"], {
      cwd: BACKEND,
      shell: false,
      env: envForBackendChild(),
    });
  } else {
    log("Tip: set START_CELERY=1 to run worker+beat (requires Redis)");
  }

  log(`Starting Vite on ${feOrigin} (API ${apiUrl})...`);
  runNpm(["run", "dev", "--", "--host", "0.0.0.0", "--port", fePort], {
    cwd: FRONTEND,
    env: feEnv,
  });

  await waitForHttp(feOrigin + "/", "Frontend", { maxWaitMs: 120000, intervalMs: 500 });

  log("Startup complete ? Ctrl+C stops all processes");
  openBrowser(feOrigin + "/");

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  await new Promise(() => {});
}

main().catch((err) => {
  console.error("[start] Fatal:", err.message);
  process.exit(1);
});
