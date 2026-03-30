/**
 * One-shot dev startup: Docker Postgres/Redis (optional), backend venv + deps + migrations,
 * frontend npm install, then uvicorn + Vite (and optional Celery for device polling).
 *
 * Usage: node start.js
 * Env:   PYTHON=path\to\python.exe  START_CELERY=1  SKIP_DOCKER=1  START_JS_NO_ENV_SYNC=1
 *
 * Docker Compose must live at ./docker-compose.yml (repo root). Host DB/Redis ports are
 * 5433 and 6380 so a local PostgreSQL on 5432 does not collide.
 */

const { spawn, execFileSync, execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname);
const BACKEND = path.join(ROOT, "backend");
const FRONTEND = path.join(ROOT, "frontend");
const COMPOSE_FILE = path.join(ROOT, "docker-compose.yml");
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

function dockerComposeAvailable() {
  try {
    execFileSync("docker", ["compose", "version"], { stdio: "ignore" });
    return "docker";
  } catch {
    try {
      execFileSync("docker-compose", ["version"], { stdio: "ignore" });
      return "docker-compose";
    } catch {
      return null;
    }
  }
}

/** True if the Docker engine is accepting commands (Desktop running on Windows). */
function dockerEngineRunning() {
  try {
    execFileSync("docker", ["info"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/**
 * Run compose with an absolute -f path so it works regardless of cwd quirks on Windows.
 */
function dockerComposeRun(cli, composeArgs) {
  if (!fs.existsSync(COMPOSE_FILE)) {
    throw new Error(`Missing ${COMPOSE_FILE}`);
  }
  const f = COMPOSE_FILE;
  if (cli === "docker") {
    execFileSync("docker", ["compose", "-f", f, ...composeArgs], {
      cwd: ROOT,
      stdio: "inherit",
    });
  } else {
    execFileSync("docker-compose", ["-f", f, ...composeArgs], {
      cwd: ROOT,
      stdio: "inherit",
    });
  }
}

async function waitForPostgres(cli) {
  const f = COMPOSE_FILE;
  for (let i = 0; i < 45; i++) {
    try {
      if (cli === "docker") {
        execFileSync(
          "docker",
          ["compose", "-f", f, "exec", "-T", "postgres", "pg_isready", "-U", "biometric", "-d", "biometric"],
          { cwd: ROOT, stdio: "ignore" }
        );
      } else {
        execFileSync(
          "docker-compose",
          ["-f", f, "exec", "-T", "postgres", "pg_isready", "-U", "biometric", "-d", "biometric"],
          { cwd: ROOT, stdio: "ignore" }
        );
      }
      return true;
    } catch {
      await sleep(1000);
    }
  }
  return false;
}

/**
 * Point backend/.env at Docker-published ports (5433 / 6380).
 * Run whenever not using SKIP_DOCKER — even if Docker failed to start — so we never hit
 * localhost:5432 (wrong local Postgres) by mistake.
 */
function syncBackendEnvForDockerHostPorts() {
  const envPath = path.join(BACKEND, ".env");
  if (!fs.existsSync(envPath)) return;
  const dbUrl = "postgresql+psycopg://biometric:biometric@localhost:5433/biometric";
  const redisUrl = "redis://localhost:6380/0";
  let c = fs.readFileSync(envPath, "utf8");
  let changed = false;

  const dbLineOk =
    /^DATABASE_URL=.*:5433\b/m.test(c) ||
    /^DATABASE_URL=.*:5433\//m.test(c);
  const redisLineOk = /^REDIS_URL=.*6380\b/m.test(c);

  if (!dbLineOk) {
    c = c.replace(/^DATABASE_URL=.*$/m, `DATABASE_URL=${dbUrl}`);
    changed = true;
  }
  if (!redisLineOk) {
    c = c.replace(/^REDIS_URL=.*$/m, `REDIS_URL=${redisUrl}`);
    changed = true;
  }
  if (changed) {
    fs.writeFileSync(envPath, c, "utf8");
    log("Set backend/.env DATABASE_URL/REDIS_URL to host ports Postgres 5433, Redis 6380 (docker-compose.yml)");
  }
}

function ensureBackendEnv() {
  const envPath = path.join(BACKEND, ".env");
  const example = path.join(BACKEND, ".env.example");
  if (!fs.existsSync(envPath) && fs.existsSync(example)) {
    fs.copyFileSync(example, envPath);
    log("Created backend/.env from .env.example");
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
  log("Creating backend virtualenv…");
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

/**
 * Inherited shell env often has DATABASE_URL=...@localhost:5432, which overrides backend/.env.
 * Drop these so pydantic loads DATABASE_URL / REDIS_URL from backend/.env only.
 */
function envForBackendChild(extra = {}) {
  const e = { ...process.env, PYTHONPATH: BACKEND, ...extra };
  delete e.DATABASE_URL;
  delete e.REDIS_URL;
  return e;
}

async function pipInstall() {
  log("Installing Python dependencies…");
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
  log("Running database migrations…");
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
      "Alembic failed — ensure Postgres is reachable (docker compose up -d postgres redis from repo root)"
    );
    throw new Error(`alembic upgrade failed with exit ${code}`);
  }
}

async function npmInstallFrontend() {
  if (fs.existsSync(path.join(FRONTEND, "node_modules"))) {
    log("Frontend node_modules present; skipping npm install");
    return;
  }
  log("Installing frontend dependencies (npm install)…");
  const npmCmd = isWin ? "npm.cmd" : "npm";
  const r = spawn(npmCmd, ["install"], { cwd: FRONTEND, stdio: "inherit", shell: false });
  const code = await waitForExit(r);
  if (code !== 0) throw new Error(`npm install failed with exit ${code}`);
}

function shutdown() {
  log("Shutting down…");
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
  log("Biometric attendance — dev startup");
  process.chdir(ROOT);

  if (!fs.existsSync(BACKEND) || !fs.existsSync(FRONTEND)) {
    throw new Error("Expected backend/ and frontend/ next to start.js");
  }

  let dockerStarted = false;
  const cli = dockerComposeAvailable();

  if (process.env.SKIP_DOCKER !== "1" && cli) {
    if (!fs.existsSync(COMPOSE_FILE)) {
      warn(`No ${COMPOSE_FILE} — cannot start Postgres/Redis via Docker. Add docker-compose.yml or set SKIP_DOCKER=1`);
    } else if (!dockerEngineRunning()) {
      warn(
        "Docker CLI is installed but the Docker engine is not running (Docker Desktop not started on Windows). " +
          "Start Docker Desktop, wait until it is idle, then run this script again."
      );
    } else {
      try {
        log("Starting Postgres & Redis (docker compose)…");
        dockerComposeRun(cli, ["up", "-d", "postgres", "redis"]);
        const ok = await waitForPostgres(cli);
        if (!ok) warn("Postgres did not become ready in time; migrations may fail.");
        else {
          log("Postgres is ready");
          dockerStarted = true;
        }
      } catch (e) {
        const msg = String(e && e.message ? e.message : e);
        warn(`Docker compose failed: ${msg}`);
        if (/pipe\\dockerDesktopLinuxEngine|dockerDesktopLinuxEngine|cannot find the file specified/i.test(msg)) {
          warn(
            "This usually means Docker Desktop is not running. Start Docker Desktop and retry."
          );
        }
      }
    }
  } else if (process.env.SKIP_DOCKER === "1") {
    log("SKIP_DOCKER=1 — using backend/.env as-is (no port rewrite)");
  } else {
    warn("Docker not found — install Docker Desktop or start Postgres/Redis yourself");
  }

  ensureBackendEnv();
  if (process.env.SKIP_DOCKER !== "1" && process.env.START_JS_NO_ENV_SYNC !== "1") {
    syncBackendEnvForDockerHostPorts();
  }

  await ensureVenv();
  await pipInstall();
  await alembicUpgrade();
  await npmInstallFrontend();

  const apiUrl = process.env.VITE_API_URL || "http://localhost:8000";
  const feEnv = { ...process.env, VITE_API_URL: apiUrl };

  log("Starting FastAPI (uvicorn) on http://0.0.0.0:8000 …");
  run(VENV_PY, ["-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"], {
    cwd: BACKEND,
    shell: false,
    env: envForBackendChild(),
  });

  if (process.env.START_CELERY === "1") {
    log("Starting Celery worker + beat (device polling)…");
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
    log("Tip: set START_CELERY=1 to run worker+beat for biometric polling");
  }

  await sleep(1500);

  log(`Starting Vite on http://localhost:5173 (API ${apiUrl})…`);
  const npmCmd = isWin ? "npm.cmd" : "npm";
  run(npmCmd, ["run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"], {
    cwd: FRONTEND,
    shell: false,
    env: feEnv,
  });

  log("App starting — Ctrl+C stops all processes");
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error("[start] Fatal:", err.message);
  process.exit(1);
});
