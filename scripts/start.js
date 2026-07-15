/**
 * Local dev startup: backend venv + pip, Alembic migrations, frontend npm install, uvicorn + Vite.
 * Requires PostgreSQL (and Redis if you use START_CELERY=1). Configure backend/.env first.
 *
 * Usage: npm start | node start.js | node scripts/start.js
 * Env:   PYTHON=path\to\python.exe   START_CELERY=1   SKIP_OPEN_BROWSER=1
 *        FRONTEND_PORT=5173   VITE_API_URL=/api
 *        VITE_DEV_PROXY_TARGET=http://localhost:8000
 */

const { spawn, execSync } = require("child_process");
const http = require("http");
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
      "Run from the repository root via `npm start` or `node start.js`."
  );
}

const ROOT = resolveRepoRoot(__dirname);
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

async function checkPostgresConnectivity() {
  log("Checking PostgreSQL connectivity...");
  const pyScript = `
import sys
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
url = str(settings.database_url)
host = settings.db_host or "unknown"
port = settings.db_port or 5432
try:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("OK")
except Exception as exc:
    msg = str(exc).lower()
    if "password authentication failed" in msg:
        print(f"AUTH_FAIL|{host}|{port}")
    elif "does not exist" in msg and "database" in msg:
        print(f"NO_DB|{settings.db_name}")
    elif "connection refused" in msg:
        print(f"REFUSED|{host}|{port}")
    elif "server closed the connection" in msg:
        print(f"SERVER_CLOSED|{host}|{port}")
    elif "timeout" in msg or "unreachable" in msg:
        print(f"TIMEOUT|{host}|{port}")
    elif "connection failed" in msg or "could not connect" in msg:
        print(f"UNREACHABLE|{host}|{port}")
    else:
        print(f"ERROR|{exc}")
    sys.exit(1)
`;
  const r = spawn(VENV_PY, ["-c", pyScript], {
    cwd: BACKEND,
    stdio: ["ignore", "pipe", "inherit"],
    shell: false,
    env: envForBackendChild(),
  });
  let stdout = "";
  r.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });
  const code = await waitForExit(r);
  const line = stdout.trim().split("\n").pop() || "";
  if (code === 0 && line === "OK") {
    log("PostgreSQL connection OK");
    return;
  }
  const [kind, a, b] = line.split("|");
  if (kind === "REFUSED") {
    warn(
      `Nothing is listening on ${a}:${b} (connection refused). ` +
        "On the VM, start PostgreSQL and confirm it listens on that port (postgresql.conf / docker publish). " +
        "For local WSL dev, use DB_HOST=127.0.0.1, DB_PORT=5432 in backend/.env."
    );
  } else if (kind === "SERVER_CLOSED") {
    warn(
      `PostgreSQL at ${a}:${b} closed the connection (wrong port, pg_hba.conf, or service not ready). ` +
        "Verify the port, that postgres is running, and pg_hba allows your WSL IP."
    );
  } else if (kind === "TIMEOUT" || kind === "UNREACHABLE") {
    warn(
      `Cannot reach PostgreSQL at ${a}:${b} (network timeout or unreachable). ` +
        "If you use the VM database (192.168.1.116), connect to the LAN/VPN first. " +
        "For local WSL dev, set DB_HOST=127.0.0.1, DB_PORT=5432, and DATABASE_URL with your local postgres password in backend/.env."
    );
  } else if (kind === "AUTH_FAIL") {
    warn(
      `PostgreSQL rejected the password for user in backend/.env (${a}:${b}). ` +
        "Update DB_PASSWORD and DATABASE_URL with the correct postgres password."
    );
  } else if (kind === "NO_DB") {
    warn(
      `Database "${a}" does not exist. Create it with backend/scripts/setup_local_database.sql, then rerun start.js.`
    );
  } else {
    warn(`PostgreSQL check failed: ${line.replace(/^ERROR\|/, "")}`);
  }
  throw new Error("PostgreSQL is not reachable with backend/.env settings");
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
      "Alembic failed ? check PostgreSQL is running, database exists, and backend/.env has valid DATABASE_URL or DB_* PostgreSQL settings."
    );
    throw new Error(`alembic upgrade failed with exit ${code}`);
  }
}

async function npmInstallFrontend() {
  const hasRootModules = fs.existsSync(path.join(ROOT, "node_modules"));
  if (hasRootModules && hasViteBinary()) {
    log("Workspace dependencies present; skipping npm install");
    return;
  }
  if (hasRootModules && !hasViteBinary()) {
    warn("node_modules exists but vite binary is missing — reinstalling workspace dependencies");
  } else {
    log("Installing workspace dependencies (npm install at repo root)...");
  }
  const r = runNpm(["install"], { cwd: ROOT });
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
    throw new Error(`Expected backend/ and frontend/ at repository root (${ROOT})`);
  }

  ensureBackendEnv();

  const envPath = path.join(BACKEND, ".env");
  if (fs.existsSync(envPath)) {
    const raw = fs.readFileSync(envPath, "utf8");
    if (/YOUR_PASSWORD|CHANGE_ME/i.test(raw)) {
      warn(
        "backend/.env still contains YOUR_PASSWORD or CHANGE_ME ? set DATABASE_URL (or DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD) to real PostgreSQL credentials."
      );
    }
  }

  await ensureVenv();
  await pipInstall();
  await checkPostgresConnectivity();
  await alembicUpgrade();
  await npmInstallFrontend();

  const apiUrl = process.env.VITE_API_URL || "/api";
  const devProxyTarget = process.env.VITE_DEV_PROXY_TARGET || "http://localhost:8000";
  const apiHealth = devProxyTarget.replace(/\/$/, "") + "/health";
  const fePort = process.env.FRONTEND_PORT || "5173";
  const feOrigin = `http://localhost:${fePort}`;
  const feEnv = { ...process.env, VITE_API_URL: apiUrl, VITE_DEV_PROXY_TARGET: devProxyTarget };

  log("Starting FastAPI (uvicorn) on http://0.0.0.0:8000 ...");
  run(VENV_PY, ["-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"], {
    cwd: BACKEND,
    shell: false,
    env: envForBackendChild(),
  });

  await waitForHttp(apiHealth, "API", { maxWaitMs: 120000, intervalMs: 500 });

  // Auto-start worker+beat when Redis is expected (device polls every DEVICE_POLL_INTERVAL_SECONDS).
  // Set START_CELERY=0 to skip. Explicit START_CELERY=1 always starts them.
  const startCelery =
    process.env.START_CELERY === "1" ||
    (process.env.START_CELERY !== "0" && process.env.DEVICE_AUTO_SYNC_ENABLED !== "false");
  if (startCelery) {
    log("Starting Celery worker + beat (device auto-sync; needs Redis on REDIS_URL)...");
    run(VENV_PY, ["-m", "celery", "-A", "app.workers.celery_app", "worker", "-l", "info", "-Q", "attendance"], {
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
    log("Celery skipped (START_CELERY=0). Manual Sync still works from the UI.");
  }

  log(`Starting Vite on ${feOrigin} (API base ${apiUrl}, dev proxy ${devProxyTarget})...`);
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
