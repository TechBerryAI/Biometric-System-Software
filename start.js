/**
 * Local dev startup: backend venv + pip, Alembic migrations, frontend npm install, uvicorn + Vite.
 * Requires PostgreSQL (and Redis if you use START_CELERY=1) — configure backend/.env first.
 *
 * Usage: node start.js
 * Env:   PYTHON=path\to\python.exe  START_CELERY=1
 */

const { spawn, execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname);
const BACKEND = path.join(ROOT, "backend");
const FRONTEND = path.join(ROOT, "frontend");
const VENV_PY = path.join(
  BACKEND,
  ".venv",
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
    log("Created backend/.env from .env.example — edit DATABASE_URL (password) before continuing.");
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
  if (fs.existsSync(VENV_PY)) {
    log("Backend virtualenv already exists");
    return;
  }
  log("Creating backend virtualenv...");
  const { cmd, argsPrefix } = resolvePythonLauncher();
  const args = [...argsPrefix, "-m", "venv", ".venv"];
  const r = spawn(cmd, args, { cwd: BACKEND, stdio: "inherit", shell: isWin });
  const code = await waitForExit(r);
  if (code !== 0) throw new Error(`venv creation failed with exit ${code}`);
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

async function pipInstall() {
  log("Installing Python dependencies...");
  const py = fs.existsSync(VENV_PY) ? VENV_PY : "python";
  const r = spawn(py, ["-m", "pip", "install", "-r", "requirements.txt"], {
    cwd: BACKEND,
    stdio: "inherit",
    shell: false,
  });
  const code = await waitForExit(r);
  if (code !== 0) throw new Error(`pip install failed with exit ${code}`);
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
      "Alembic failed — check PostgreSQL is running, database exists, and DATABASE_URL in backend/.env is correct."
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
    warn("node_modules exists but vite binary is missing — reinstalling frontend dependencies");
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
  log("Biometric attendance — dev startup (local PostgreSQL)");
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
        "backend/.env still contains YOUR_PASSWORD or CHANGE_ME — set DATABASE_URL to your real PostgreSQL password."
      );
    }
  }

  await ensureVenv();
  await pipInstall();
  await alembicUpgrade();
  await npmInstallFrontend();

  const apiUrl = process.env.VITE_API_URL || "http://localhost:8000";
  const feEnv = { ...process.env, VITE_API_URL: apiUrl };

  log("Starting FastAPI (uvicorn) on http://0.0.0.0:8000 ...");
  run(VENV_PY, ["-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"], {
    cwd: BACKEND,
    shell: false,
    env: envForBackendChild(),
  });

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

  await sleep(1500);

  log(`Starting Vite on http://localhost:5173 (API ${apiUrl})...`);
  runNpm(["run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"], {
    cwd: FRONTEND,
    env: feEnv,
  });

  log("App starting — Ctrl+C stops all processes");
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  // Keep parent process alive while child services are running.
  await new Promise(() => {});
}

main().catch((err) => {
  console.error("[start] Fatal:", err.message);
  process.exit(1);
});
