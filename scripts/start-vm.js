#!/usr/bin/env node
/**
 * Biometrica stack runner for the VM (production) and for local development.
 *
 *   node start-vm.js                  Production: check PostgreSQL/Redis -> migrations -> build the
 *                                     frontend when its sources changed -> start a supervised API
 *                                     (uvicorn workers), Celery worker + beat, and the web server.
 *   START_MODE=dev node start-vm.js   Development: uvicorn --reload + Vite dev server (`make start`).
 *
 * Crashed services restart automatically with backoff. Ctrl+C / SIGTERM / SIGHUP stops everything,
 * including grandchildren (uvicorn workers, Celery pool processes). Processes left behind by an
 * earlier run that was killed abruptly are cleaned up on the next start.
 *
 * Env (all optional):
 *   VM_HOST=192.168.1.60              address shown in the startup banner
 *   API_PORT=8000  FRONTEND_PORT=5173  API_BIND_HOST=0.0.0.0  FRONTEND_BIND_HOST=0.0.0.0
 *   API_WORKERS=2                     uvicorn worker processes (production)
 *   START_CELERY=1|0                  Celery worker + beat (default on unless DEVICE_AUTO_SYNC_ENABLED=false)
 *   CELERY_CONCURRENCY=4              Celery pool processes
 *   SERVICE_WAIT_SECONDS=...          give up if PostgreSQL/Redis are still down after this long
 *                                     (default: production waits until they recover; dev waits 60s)
 *   FRONTEND_BUILD=auto|always|never  rebuild frontend/dist (auto = only when sources changed)
 *   VITE_API_URL=/api  OPEN_BROWSER=1
 */

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");
const readline = require("readline");

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
const DIST = path.join(FRONTEND, "dist");
const RUN_DIR = path.join(ROOT, ".run");
const LOCK_FILE = path.join(RUN_DIR, "start-vm.pid");
const CHILDREN_FILE = path.join(RUN_DIR, "children.json");
const isWin = process.platform === "win32";
const isLinux = process.platform === "linux";

const DEV = (process.env.START_MODE || "").toLowerCase() === "dev" || process.argv.includes("--dev");
const VM_HOST = process.env.VM_HOST || "192.168.1.60";
const API_PORT = process.env.API_PORT || "8000";
const FRONTEND_PORT = process.env.FRONTEND_PORT || "5173";
const API_BIND_HOST = process.env.API_BIND_HOST || "0.0.0.0";
const FRONTEND_BIND_HOST = process.env.FRONTEND_BIND_HOST || "0.0.0.0";
const API_WORKERS = String(Math.max(1, Number(process.env.API_WORKERS) || 2));
const CELERY_CONCURRENCY = String(Math.max(1, Number(process.env.CELERY_CONCURRENCY) || 4));
// Unset in production = wait until the database/Redis come back, then start on its own.
const SERVICE_WAIT_SECONDS = process.env.SERVICE_WAIT_SECONDS || (DEV ? "60" : "");
const FRONTEND_BUILD = (process.env.FRONTEND_BUILD || "auto").toLowerCase();
const VITE_API_URL = process.env.VITE_API_URL || "/api";
const CELERY_QUEUES = "attendance_sync,device_commands,reconciliation,notifications";
const STOP_TIMEOUT_MS = 30_000;
// Per-process pool sizes keep the total under PostgreSQL's default max_connections (100).
const ROLE_DB_POOLS = { api: ["5", "10"], worker: ["2", "3"], beat: ["1", "1"] };

const useColor = Boolean(process.stdout.isTTY) && !process.env.NO_COLOR;
const paint = (code, text) => (useColor ? `\x1b[${code}m${text}\x1b[0m` : text);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function log(msg) {
  console.log(`${paint(36, "[start-vm]")} ${msg}`);
}

function warn(msg) {
  console.warn(`${paint(33, "[start-vm]")} ${msg}`);
}

// A closed terminal must not crash the supervisor while it is shutting services down.
process.stdout.on("error", () => {});
process.stderr.on("error", () => {});

// ---------------------------------------------------------------- environment

function readDotenv(file) {
  const values = {};
  if (!fs.existsSync(file)) return values;
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (match) values[match[1]] = match[2].replace(/^(['"])(.*)\1$/, "$2");
  }
  return values;
}

function ensureEnvFile(dir, note) {
  const envPath = path.join(dir, ".env");
  const example = path.join(dir, ".env.example");
  if (!fs.existsSync(envPath) && fs.existsSync(example)) {
    fs.copyFileSync(example, envPath);
    log(`Created ${path.relative(ROOT, envPath)} from .env.example; ${note}`);
  }
}

let backendDotenv = {};

function isConfigured(key) {
  return process.env[key] !== undefined || backendDotenv[key] !== undefined;
}

function backendEnv(role, extra = {}) {
  const env = { ...process.env, PYTHONPATH: BACKEND, PYTHONUNBUFFERED: "1", ...extra };
  // backend/.env is the source of truth for connection strings; a stale shell export must not win.
  delete env.DATABASE_URL;
  delete env.REDIS_URL;
  if (!isConfigured("DB_APPLICATION_NAME")) env.DB_APPLICATION_NAME = `biometrica-${role}`;
  const pool = ROLE_DB_POOLS[role];
  if (pool && !isConfigured("DB_POOL_SIZE")) env.DB_POOL_SIZE = pool[0];
  if (pool && !isConfigured("DB_MAX_OVERFLOW")) env.DB_MAX_OVERFLOW = pool[1];
  return env;
}

function celeryEnabled() {
  if (process.env.START_CELERY === "1") return true;
  if (process.env.START_CELERY === "0") return false;
  const autoSync = process.env.DEVICE_AUTO_SYNC_ENABLED ?? backendDotenv.DEVICE_AUTO_SYNC_ENABLED;
  return String(autoSync ?? "true").toLowerCase() !== "false";
}

function venvPythonPath(venvDir) {
  return path.join(venvDir, isWin ? "Scripts" : "bin", isWin ? "python.exe" : "python");
}

function resolveBackendPython() {
  const override = process.env.BACKEND_VENV_PY;
  if (override && fs.existsSync(override)) return override;
  for (const dir of [".venv", "venv", "env"]) {
    const candidate = venvPythonPath(path.join(BACKEND, dir));
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error(
    "Missing backend venv python. Expected one of backend/.venv, backend/venv, backend/env (or set BACKEND_VENV_PY)."
  );
}

function hasViteBinary() {
  return [ROOT, FRONTEND].some((dir) =>
    ["vite", "vite.cmd"].some((bin) => fs.existsSync(path.join(dir, "node_modules", ".bin", bin)))
  );
}

function npmCommand(args) {
  return isWin ? ["cmd.exe", ["/d", "/s", "/c", "npm", ...args]] : ["npm", args];
}

// ---------------------------------------------------------------- single instance + leftovers

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === "EPERM";
  }
}

function procInfo(pid) {
  try {
    const cmdline = fs.readFileSync(`/proc/${pid}/cmdline`, "utf8").split("\0").join(" ").trim();
    let cwd = "";
    try {
      cwd = fs.readlinkSync(`/proc/${pid}/cwd`);
    } catch {
      /* owned by another user */
    }
    return { cmdline, cwd };
  } catch {
    return null;
  }
}

let ownsInstanceLock = false;

function acquireInstanceLock() {
  fs.mkdirSync(RUN_DIR, { recursive: true });
  if (fs.existsSync(LOCK_FILE)) {
    const pid = Number(fs.readFileSync(LOCK_FILE, "utf8").trim());
    if (pid && pid !== process.pid && isAlive(pid)) {
      const info = isLinux ? procInfo(pid) : null;
      if (!info || info.cmdline.includes("start-vm")) {
        throw new Error(
          `Biometrica is already running (pid ${pid}). Stop it first: Ctrl+C in its terminal, ` +
            `\`kill ${pid}\`, or \`sudo systemctl stop biometrica\` if it runs as a service.`
        );
      }
    }
  }
  fs.writeFileSync(LOCK_FILE, String(process.pid));
  ownsInstanceLock = true;
}

function releaseInstanceLock() {
  if (!ownsInstanceLock) return;
  try {
    fs.unlinkSync(CHILDREN_FILE);
  } catch {
    /* nothing recorded */
  }
  try {
    if (Number(fs.readFileSync(LOCK_FILE, "utf8").trim()) === process.pid) fs.unlinkSync(LOCK_FILE);
  } catch {
    /* already gone */
  }
}

/** API / Celery / web processes started from this checkout (by any earlier runner). */
function isStackProcess(info) {
  if (info.cwd === BACKEND) {
    // uvicorn master, Celery main + forked pool children, uvicorn/reload workers (multiprocessing spawn).
    return /app\.main:app|app\.workers\.celery_app|--multiprocessing-fork/.test(info.cmdline);
  }
  if (info.cwd === FRONTEND) {
    return /node_modules\/\.bin\/vite|vite\/bin\/vite\.js|^sh -c vite\b|\bnpm\b.* run dev\b|esbuild --service/.test(
      info.cmdline
    );
  }
  return info.cmdline.includes(path.join(ROOT, "scripts", "serve-frontend.js"));
}

async function cleanupLeftoverProcesses() {
  const victims = new Map();
  let recorded = [];
  try {
    recorded = JSON.parse(fs.readFileSync(CHILDREN_FILE, "utf8"));
  } catch {
    /* first run or clean shutdown */
  }

  if (isLinux) {
    for (const entry of fs.readdirSync("/proc")) {
      if (!/^\d+$/.test(entry)) continue;
      const pid = Number(entry);
      if (pid === process.pid || pid === process.ppid) continue;
      const info = procInfo(pid);
      if (info && isStackProcess(info)) victims.set(pid, info.cmdline.slice(0, 90));
    }
  } else {
    for (const child of recorded) {
      if (child.pid && isAlive(child.pid)) victims.set(child.pid, child.name);
    }
  }
  if (victims.size === 0) return;

  warn(`Stopping ${victims.size} leftover process(es) from a previous run:`);
  for (const [pid, label] of victims) warn(`  pid ${pid}: ${label}`);
  const pids = [...victims.keys()];
  for (const pid of pids) {
    try {
      if (isWin) spawnSync("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" });
      else process.kill(pid, "SIGTERM");
    } catch (err) {
      if (err.code === "EPERM") warn(`  pid ${pid} belongs to another user; stop it with: sudo kill ${pid}`);
    }
  }
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline && pids.some(isAlive)) await sleep(250);
  for (const pid of pids.filter(isAlive)) {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      /* gone or not ours */
    }
  }
}

function isPortInUse(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    const done = (inUse) => {
      socket.destroy();
      resolve(inUse);
    };
    socket.setTimeout(800);
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
    socket.once("timeout", () => done(false));
    socket.connect(Number(port), "127.0.0.1");
  });
}

async function assertPortsFree() {
  for (const [port, label] of [
    [API_PORT, "API"],
    [FRONTEND_PORT, "Web"],
  ]) {
    if (await isPortInUse(port)) {
      throw new Error(
        `${label} port ${port} is in use by another program. Find it with: sudo ss -ltnp 'sport = :${port}'`
      );
    }
  }
}

// ---------------------------------------------------------------- one-shot steps

// The one-shot step currently running (preflight / migrations / build), so a stop request can end it.
let activeStep = null;

function runStep(label, command, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit", windowsHide: true, ...options });
    activeStep = child;
    child.on("error", (err) => {
      activeStep = null;
      reject(new Error(`${label} could not start: ${err.message}`));
    });
    child.on("exit", (code) => {
      activeStep = null;
      resolve(code === 0);
    });
  });
}

async function runPreflight(python, { skipRedis }) {
  const label = skipRedis ? "PostgreSQL" : "PostgreSQL and Redis";
  const args = [path.join("scripts", "check_services.py")];
  if (SERVICE_WAIT_SECONDS) {
    log(`Checking ${label} (waiting up to ${SERVICE_WAIT_SECONDS}s) ...`);
    args.push("--wait", SERVICE_WAIT_SECONDS);
  } else {
    log(`Checking ${label} (waits until they are reachable; Ctrl+C to stop) ...`);
    args.push("--forever");
  }
  if (skipRedis) args.push("--skip-redis");
  if (!(await runStep("Preflight", python, args, { cwd: BACKEND, env: backendEnv("preflight") }))) {
    throw new Error("Required services are not reachable (details above). Nothing was started.");
  }
}

async function runMigrations(python) {
  log("Applying database migrations (alembic upgrade head) ...");
  const ok = await runStep("Migrations", python, ["-m", "alembic", "upgrade", "head"], {
    cwd: BACKEND,
    env: backendEnv("migrate"),
  });
  if (!ok) {
    throw new Error("Database migrations failed (details above). Nothing was started.");
  }
}

const BUILD_INPUTS = [
  "src",
  "public",
  "index.html",
  "package.json",
  "vite.config.ts",
  "tailwind.config.js",
  "postcss.config.js",
  "tsconfig.json",
  "tsconfig.app.json",
  "tsconfig.node.json",
  ".env",
].map((p) => path.join(FRONTEND, p));
BUILD_INPUTS.push(path.join(ROOT, "package-lock.json"));

function newestMtime(target) {
  let stat;
  try {
    stat = fs.statSync(target);
  } catch {
    return 0;
  }
  if (!stat.isDirectory()) return stat.mtimeMs;
  let newest = stat.mtimeMs;
  for (const name of fs.readdirSync(target)) {
    if (name === "node_modules") continue;
    newest = Math.max(newest, newestMtime(path.join(target, name)));
  }
  return newest;
}

function frontendBuildReason() {
  if (FRONTEND_BUILD === "always") return "FRONTEND_BUILD=always";
  if (!fs.existsSync(path.join(DIST, "index.html"))) return "no build yet";
  if (FRONTEND_BUILD === "never") return null;
  let stamp = null;
  try {
    stamp = JSON.parse(fs.readFileSync(path.join(DIST, ".build-stamp.json"), "utf8"));
  } catch {
    return "build stamp missing";
  }
  if (stamp.viteApiUrl !== VITE_API_URL) return `VITE_API_URL changed to ${VITE_API_URL}`;
  if (Math.max(...BUILD_INPUTS.map(newestMtime)) > stamp.builtAtMs) return "frontend sources changed";
  return null;
}

async function buildFrontend(reason) {
  if (!hasViteBinary()) {
    throw new Error("Frontend dependencies are missing (vite). Run `npm install` at the repository root.");
  }
  log(`Building frontend (${reason}) ...`);
  const startedAt = Date.now();
  const next = path.join(FRONTEND, "dist.next");
  const prev = path.join(FRONTEND, "dist.prev");
  fs.rmSync(next, { recursive: true, force: true });
  const [cmd, args] = npmCommand(["run", "build", "--", "--outDir", "dist.next", "--emptyOutDir"]);
  const ok = await runStep("Frontend build", cmd, args, { cwd: FRONTEND, env: { ...process.env, VITE_API_URL } });
  if (stopping) return;
  if (!ok) {
    fs.rmSync(next, { recursive: true, force: true });
    if (fs.existsSync(path.join(DIST, "index.html"))) {
      warn("Frontend build failed; continuing with the previous build.");
      return;
    }
    throw new Error("Frontend build failed (details above).");
  }
  fs.writeFileSync(
    path.join(next, ".build-stamp.json"),
    JSON.stringify({ builtAtMs: startedAt, viteApiUrl: VITE_API_URL })
  );
  // Swap directories so a failed build never leaves the site half-written.
  fs.rmSync(prev, { recursive: true, force: true });
  if (fs.existsSync(DIST)) fs.renameSync(DIST, prev);
  fs.renameSync(next, DIST);
  fs.rmSync(prev, { recursive: true, force: true });
  log(`Frontend built in ${((Date.now() - startedAt) / 1000).toFixed(1)}s.`);
}

function resetBeatState() {
  // The schedule is a shelve DB that corrupts on hard kills or Python upgrades; beat rebuilds it.
  for (const [dir, pattern] of [
    [RUN_DIR, /^celerybeat/],
    [BACKEND, /^celerybeat-schedule|^celerybeat\.pid$/],
  ]) {
    for (const name of fs.readdirSync(dir)) {
      if (pattern.test(name)) fs.rmSync(path.join(dir, name), { force: true });
    }
  }
}

// ---------------------------------------------------------------- supervision

let stopping = false;
const services = [];

function pipeLines(stream, prefix, target) {
  readline.createInterface({ input: stream, crlfDelay: Infinity }).on("line", (line) => {
    target.write(`${prefix} ${line}\n`);
  });
}

function recordChildren() {
  if (!ownsInstanceLock) return;
  const live = services.filter((s) => s.child && s.child.pid).map((s) => ({ name: s.name, pid: s.child.pid }));
  try {
    fs.writeFileSync(CHILDREN_FILE, JSON.stringify(live));
  } catch {
    /* best effort */
  }
}

class Service {
  constructor({ name, color, command, args, cwd, env }) {
    Object.assign(this, { name, color, command, args, cwd, env });
    this.child = null;
    this.timer = null;
    this.failures = 0;
    this.startedAt = 0;
    services.push(this);
  }

  start() {
    if (stopping) return;
    this.startedAt = Date.now();
    const child = spawn(this.command, this.args, {
      cwd: this.cwd,
      env: this.env,
      stdio: ["ignore", "pipe", "pipe"],
      // Own process group on POSIX so stop/kill reaches uvicorn workers and Celery pool children.
      detached: !isWin,
      windowsHide: true,
    });
    this.child = child;
    const prefix = paint(this.color, `[${this.name}]`.padEnd(9));
    pipeLines(child.stdout, prefix, process.stdout);
    pipeLines(child.stderr, prefix, process.stderr);
    let exited = false;
    const onExit = (code, signal) => {
      if (exited) return;
      exited = true;
      this.handleExit(child, code, signal);
    };
    child.on("exit", onExit);
    child.on("error", (err) => {
      warn(`${this.name} could not start: ${err.message}`);
      if (!child.pid) onExit(null, null);
    });
    recordChildren();
  }

  handleExit(child, code, signal) {
    if (this.child === child) this.child = null;
    // Leader gone: clear anything it left in its process group (orphaned workers hold the port).
    this.killGroup(child, "SIGKILL");
    recordChildren();
    if (stopping) return;
    if (Date.now() - this.startedAt > 60_000) this.failures = 0;
    const delay = Math.min(30_000, 1000 * 2 ** this.failures);
    this.failures += 1;
    warn(`${this.name} exited (${signal ? `signal ${signal}` : `code ${code}`}); restarting in ${delay / 1000}s`);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.start();
    }, delay);
  }

  killGroup(child, signal) {
    if (!child || !child.pid) return;
    try {
      if (isWin) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
      else process.kill(-child.pid, signal);
    } catch {
      /* already gone */
    }
  }

  stop() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (!this.child) return;
    // Graceful: the leader (uvicorn master / Celery main / npm) shuts its own children down.
    if (isWin) this.killGroup(this.child, "SIGTERM");
    else {
      try {
        process.kill(this.child.pid, "SIGTERM");
      } catch {
        /* already gone */
      }
    }
  }
}

async function shutdown(code, reason) {
  if (stopping) return;
  stopping = true;
  if (reason) log(reason);
  if (activeStep) {
    try {
      if (isWin) spawnSync("taskkill", ["/pid", String(activeStep.pid), "/T", "/F"], { stdio: "ignore" });
      else activeStep.kill("SIGTERM");
    } catch {
      /* already finished */
    }
  }
  if (services.some((s) => s.child)) log("Stopping services ...");
  for (const service of services) service.stop();
  const deadline = Date.now() + STOP_TIMEOUT_MS;
  while (Date.now() < deadline && services.some((s) => s.child)) await sleep(200);
  for (const service of services) {
    if (service.child) {
      warn(`${service.name} did not stop within ${STOP_TIMEOUT_MS / 1000}s; killing it.`);
      service.killGroup(service.child, "SIGKILL");
    }
  }
  releaseInstanceLock();
  log("Stopped.");
  process.exit(code);
}

function httpOk(url, timeoutMs = 3000) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs, headers: { Connection: "close" } }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 400);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForHttp(url, label, maxWaitMs = 120_000) {
  const startedAt = Date.now();
  while (!stopping && Date.now() - startedAt < maxWaitMs) {
    if (await httpOk(url)) {
      log(`${label} is up (${url}).`);
      return true;
    }
    await sleep(500);
  }
  if (!stopping) warn(`${label} is not answering at ${url} yet; check the [${label.toLowerCase()}] lines above.`);
  return false;
}

function openBrowser(url) {
  if (process.env.OPEN_BROWSER !== "1" || process.env.SKIP_OPEN_BROWSER === "1") return;
  const [cmd, args] = isWin
    ? ["cmd.exe", ["/d", "/c", "start", "", url]]
    : [process.platform === "darwin" ? "open" : "xdg-open", [url]];
  try {
    const p = spawn(cmd, args, { detached: true, stdio: "ignore" });
    p.on("error", () => warn(`Could not open a browser; open ${url} manually.`));
    p.unref();
  } catch {
    warn(`Could not open a browser; open ${url} manually.`);
  }
}

// ---------------------------------------------------------------- services

function defineServices(python, withCelery) {
  const corsOrigins =
    process.env.CORS_ALLOW_ORIGINS ||
    [
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      `http://${VM_HOST}`,
      `http://${VM_HOST}:${FRONTEND_PORT}`,
      `http://127.0.0.1:${FRONTEND_PORT}`,
    ].join(",");

  const apiArgs = ["-m", "uvicorn", "app.main:app", "--host", API_BIND_HOST, "--port", API_PORT];
  if (DEV) {
    apiArgs.push("--reload", "--reload-dir", "app");
  } else {
    apiArgs.push(
      "--workers",
      API_WORKERS,
      // Trust X-Forwarded-For from the local web proxy so rate limits and audit logs see real client IPs.
      "--proxy-headers",
      "--forwarded-allow-ips",
      "127.0.0.1",
      "--timeout-keep-alive",
      "30",
      "--timeout-graceful-shutdown",
      "20",
      // The app already logs every request (http_request); skip the duplicate uvicorn access log.
      "--no-access-log"
    );
  }
  const api = new Service({
    name: "api",
    color: 35,
    command: python,
    args: apiArgs,
    cwd: BACKEND,
    env: backendEnv("api", { CORS_ALLOW_ORIGINS: corsOrigins }),
  });

  const background = [];
  if (withCelery) {
    background.push(
      new Service({
        name: "worker",
        color: 32,
        command: python,
        args: [
          "-m",
          "celery",
          "-A",
          "app.workers.celery_app",
          "worker",
          "-l",
          "info",
          "-Q",
          CELERY_QUEUES,
          "--concurrency",
          CELERY_CONCURRENCY,
          // Gossip/mingle/heartbeat only matter for multi-node fleets and add Redis chatter
          // plus "missed heartbeat" / clock-drift warnings on a single VM.
          "--without-gossip",
          "--without-mingle",
          "--without-heartbeat",
        ],
        cwd: BACKEND,
        env: backendEnv("worker"),
      }),
      new Service({
        name: "beat",
        color: 34,
        command: python,
        args: [
          "-m",
          "celery",
          "-A",
          "app.workers.celery_app",
          "beat",
          "-l",
          "warning",
          "--schedule",
          path.join(RUN_DIR, "celerybeat-schedule"),
        ],
        cwd: BACKEND,
        env: backendEnv("beat"),
      })
    );
  }

  let web;
  if (DEV) {
    const [cmd, args] = npmCommand(["run", "dev", "--", "--host", FRONTEND_BIND_HOST, "--port", FRONTEND_PORT, "--strictPort"]);
    web = new Service({
      name: "web",
      color: 33,
      command: cmd,
      args,
      cwd: FRONTEND,
      env: {
        ...process.env,
        VITE_API_URL,
        VITE_DEV_PROXY_TARGET: process.env.VITE_DEV_PROXY_TARGET || `http://127.0.0.1:${API_PORT}`,
      },
    });
  } else {
    web = new Service({
      name: "web",
      color: 33,
      command: process.execPath,
      args: [path.join(ROOT, "scripts", "serve-frontend.js")],
      cwd: ROOT,
      env: {
        ...process.env,
        FRONTEND_DIST: DIST,
        FRONTEND_BIND_HOST,
        FRONTEND_PORT,
        API_UPSTREAM: `http://127.0.0.1:${API_PORT}`,
      },
    });
  }
  return { api, background, web };
}

// ---------------------------------------------------------------- main

async function main() {
  const startedAt = Date.now();
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    process.on(signal, () => shutdown(0, `Received ${signal}.`));
  }
  process.chdir(ROOT);
  log(`Biometrica ${DEV ? "development" : "production"} runner (${ROOT})`);

  ensureEnvFile(BACKEND, "set real database and Redis values before continuing.");
  ensureEnvFile(FRONTEND, "VITE_API_URL=/api is served through the same origin.");
  backendDotenv = readDotenv(path.join(BACKEND, ".env"));
  if (Object.values(backendDotenv).some((v) => /YOUR_PASSWORD|CHANGE_ME/i.test(v))) {
    warn("backend/.env still contains placeholder credentials; update the DB_* values.");
  }

  acquireInstanceLock();
  await cleanupLeftoverProcesses();
  const python = resolveBackendPython();
  if (DEV && !hasViteBinary()) {
    throw new Error("Frontend dependencies are missing (vite). Run `npm install` at the repository root.");
  }
  await assertPortsFree();

  const withCelery = celeryEnabled();
  await runPreflight(python, { skipRedis: !withCelery });
  if (stopping) return;
  await runMigrations(python);
  if (stopping) return;
  if (!DEV) {
    const reason = frontendBuildReason();
    if (reason) await buildFrontend(reason);
    else log("Frontend build is up to date.");
  }
  if (withCelery) resetBeatState();

  const { api, background, web } = defineServices(python, withCelery);
  log(DEV ? "Starting API (uvicorn --reload) ..." : `Starting API (${API_WORKERS} uvicorn workers) ...`);
  api.start();
  await waitForHttp(`http://127.0.0.1:${API_PORT}/health`, "API");
  if (withCelery) {
    log(`Starting Celery worker (concurrency ${CELERY_CONCURRENCY}) and beat ...`);
    for (const service of background) service.start();
  } else {
    log("Celery disabled (START_CELERY=0 or DEVICE_AUTO_SYNC_ENABLED=false); Sync now runs inside the API request.");
  }
  web.start();
  await waitForHttp(`http://127.0.0.1:${FRONTEND_PORT}/`, "Web");
  if (stopping) return;

  const publicUrl = `http://${VM_HOST}:${FRONTEND_PORT}`;
  log(paint(32, `Ready in ${((Date.now() - startedAt) / 1000).toFixed(1)}s (${DEV ? "development" : "production"} mode)`));
  log(`  Open:        ${publicUrl}`);
  log(`  API:         ${publicUrl}${VITE_API_URL} -> 127.0.0.1:${API_PORT}`);
  log(`  Background:  ${withCelery ? `Celery worker x${CELERY_CONCURRENCY} + beat` : "disabled"}`);
  log("  Stop:        Ctrl+C (crashed services restart automatically)");
  openBrowser(`${publicUrl}/`);
}

main().catch((err) => {
  console.error(`${paint(31, "[start-vm] Fatal:")} ${err.message}`);
  shutdown(1);
});
