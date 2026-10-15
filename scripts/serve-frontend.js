#!/usr/bin/env node
/**
 * Production web server for the built frontend (frontend/dist). Node core only, no dependencies.
 *
 *  - Hashed /assets/* are served with year-long immutable caching; index.html is always revalidated.
 *  - Text assets are pre-compressed (brotli + gzip) at startup and served by Accept-Encoding.
 *  - Unknown extension-less paths fall back to index.html (client-side routing).
 *  - /api/* is proxied to FastAPI with the prefix stripped (same contract as the Vite dev proxy),
 *    forwarding the real client IP and allowing long device-sync requests.
 *
 * Started by scripts/start-vm.js in production mode; can also run standalone:
 *   FRONTEND_DIST=frontend/dist API_UPSTREAM=http://127.0.0.1:8000 node scripts/serve-frontend.js
 * Env: FRONTEND_DIST, FRONTEND_BIND_HOST=0.0.0.0, FRONTEND_PORT=5173,
 *      API_UPSTREAM=http://127.0.0.1:8000, API_PROXY_TIMEOUT_MS=600000
 */

const fs = require("fs");
const http = require("http");
const path = require("path");
const zlib = require("zlib");

const DIST = path.resolve(process.env.FRONTEND_DIST || path.join(__dirname, "..", "frontend", "dist"));
const HOST = process.env.FRONTEND_BIND_HOST || "0.0.0.0";
const PORT = Number(process.env.FRONTEND_PORT || 5173);
const UPSTREAM = new URL(process.env.API_UPSTREAM || "http://127.0.0.1:8000");
const PROXY_TIMEOUT_MS = Number(process.env.API_PROXY_TIMEOUT_MS || 600_000);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
};
const COMPRESSIBLE = new Set([".html", ".js", ".mjs", ".css", ".json", ".map", ".svg", ".txt", ".webmanifest", ".ico", ".ttf"]);
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "proxy-connection",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);
const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "SAMEORIGIN",
  "Referrer-Policy": "strict-origin-when-cross-origin",
};

function log(msg) {
  console.log(`[web] ${msg}`);
}

// ---------------------------------------------------------------- static files

/** path -> { mtimeMs, raw, etag, type, br, gzip } */
const files = new Map();

function loadFile(filePath) {
  const stat = fs.statSync(filePath);
  const cached = files.get(filePath);
  if (cached && cached.mtimeMs === stat.mtimeMs) return cached;
  const raw = fs.readFileSync(filePath);
  const ext = path.extname(filePath).toLowerCase();
  const entry = {
    mtimeMs: stat.mtimeMs,
    raw,
    etag: `W/"${stat.size.toString(16)}-${Math.floor(stat.mtimeMs).toString(16)}"`,
    type: MIME[ext] || "application/octet-stream",
    br: null,
    gzip: null,
  };
  files.set(filePath, entry);
  if (COMPRESSIBLE.has(ext) && raw.length > 1024) compressEntry(entry);
  return entry;
}

function compressEntry(entry) {
  // Async (libuv threadpool) so startup and first requests never block on brotli level 11.
  zlib.brotliCompress(
    entry.raw,
    { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11, [zlib.constants.BROTLI_PARAM_SIZE_HINT]: entry.raw.length } },
    (err, out) => {
      if (!err && out.length < entry.raw.length) entry.br = out;
    }
  );
  zlib.gzip(entry.raw, { level: 9 }, (err, out) => {
    if (!err && out.length < entry.raw.length) entry.gzip = out;
  });
}

function warmCache(dir) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) warmCache(full);
    else loadFile(full);
  }
}

function resolveStatic(pathname) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  const filePath = path.resolve(DIST, `.${path.posix.normalize(decoded)}`);
  if (filePath !== DIST && !filePath.startsWith(DIST + path.sep)) return null;
  try {
    return fs.statSync(filePath).isFile() ? filePath : undefined;
  } catch {
    return undefined;
  }
}

function sendFile(req, res, filePath, cacheControl) {
  const entry = loadFile(filePath);
  const headers = {
    ...SECURITY_HEADERS,
    "Content-Type": entry.type,
    "Cache-Control": cacheControl,
    ETag: entry.etag,
    Vary: "Accept-Encoding",
  };
  if (req.headers["if-none-match"] === entry.etag) {
    res.writeHead(304, headers);
    res.end();
    return;
  }
  const accept = String(req.headers["accept-encoding"] || "");
  let body = entry.raw;
  if (entry.br && /\bbr\b/.test(accept)) {
    body = entry.br;
    headers["Content-Encoding"] = "br";
  } else if (entry.gzip && /\bgzip\b/.test(accept)) {
    body = entry.gzip;
    headers["Content-Encoding"] = "gzip";
  }
  headers["Content-Length"] = body.length;
  res.writeHead(200, headers);
  res.end(req.method === "HEAD" ? undefined : body);
}

function serveStatic(req, res, url) {
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { Allow: "GET, HEAD" });
    res.end();
    return;
  }
  const filePath = resolveStatic(url.pathname);
  if (filePath === null) {
    res.writeHead(400);
    res.end();
    return;
  }
  if (filePath) {
    const immutable = url.pathname.startsWith("/assets/");
    sendFile(req, res, filePath, immutable ? "public, max-age=31536000, immutable" : "no-cache");
    return;
  }
  if (path.posix.extname(url.pathname) === "") {
    // Client-side route such as /employees/42: hand it to the SPA.
    sendFile(req, res, path.join(DIST, "index.html"), "no-cache");
    return;
  }
  res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8", ...SECURITY_HEADERS });
  res.end("Not found");
}

// ---------------------------------------------------------------- API proxy

const upstreamAgent = new http.Agent({ keepAlive: true, maxSockets: 256, keepAliveMsecs: 15_000 });

function clientIp(req) {
  return String(req.socket.remoteAddress || "").replace(/^::ffff:/, "");
}

function proxyApi(req, res, url) {
  const upstreamPath = (url.pathname.replace(/^\/api/, "") || "/") + url.search;
  const headers = {};
  for (const [key, value] of Object.entries(req.headers)) {
    if (!HOP_BY_HOP.has(key)) headers[key] = value;
  }
  const priorForwarded = req.headers["x-forwarded-for"];
  headers["x-forwarded-for"] = priorForwarded ? `${priorForwarded}, ${clientIp(req)}` : clientIp(req);
  headers["x-forwarded-proto"] = "http";
  headers["x-forwarded-host"] = req.headers.host || "";
  headers.host = UPSTREAM.host;

  const upstreamReq = http.request(
    {
      protocol: UPSTREAM.protocol,
      hostname: UPSTREAM.hostname,
      port: UPSTREAM.port || 80,
      method: req.method,
      path: upstreamPath,
      headers,
      agent: upstreamAgent,
      timeout: PROXY_TIMEOUT_MS,
    },
    (upstreamRes) => {
      const responseHeaders = {};
      for (const [key, value] of Object.entries(upstreamRes.headers)) {
        if (!HOP_BY_HOP.has(key)) responseHeaders[key] = value;
      }
      res.writeHead(upstreamRes.statusCode || 502, responseHeaders);
      upstreamRes.pipe(res);
    }
  );

  upstreamReq.on("timeout", () => upstreamReq.destroy(new Error("upstream timeout")));
  upstreamReq.on("error", (err) => {
    if (res.headersSent) {
      res.destroy();
      return;
    }
    const timedOut = err.message === "upstream timeout";
    res.writeHead(timedOut ? 504 : 502, { "Content-Type": "application/json", ...SECURITY_HEADERS });
    res.end(
      JSON.stringify({
        detail: timedOut
          ? "The server took too long to respond. The operation may still finish in the background."
          : "The API is not reachable right now (it may be restarting). Retry in a few seconds.",
      })
    );
  });
  // Browser went away mid-request: stop the upstream work instead of finishing it for nobody.
  res.on("close", () => {
    if (!res.writableFinished) upstreamReq.destroy();
  });
  req.pipe(upstreamReq);
}

// ---------------------------------------------------------------- server

function main() {
  if (!fs.existsSync(path.join(DIST, "index.html"))) {
    console.error(`[web] ${DIST}/index.html not found. Build the frontend first: npm run build`);
    process.exit(1);
  }
  warmCache(DIST);

  const server = http.createServer((req, res) => {
    let url;
    try {
      url = new URL(req.url || "/", "http://localhost");
    } catch {
      res.writeHead(400);
      res.end();
      return;
    }
    try {
      if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
        proxyApi(req, res, url);
      } else {
        serveStatic(req, res, url);
      }
    } catch (err) {
      console.error(`[web] ${req.method} ${url.pathname} failed: ${err.stack || err}`);
      if (!res.headersSent) res.writeHead(500);
      res.end();
    }
  });
  // Device sync requests can legitimately take minutes; Node's 5-minute default would cut them off.
  server.requestTimeout = PROXY_TIMEOUT_MS + 30_000;
  server.headersTimeout = 60_000;
  server.keepAliveTimeout = 65_000;

  server.on("error", (err) => {
    console.error(`[web] cannot listen on ${HOST}:${PORT}: ${err.message}`);
    process.exit(1);
  });
  server.listen(PORT, HOST, () => {
    log(`serving ${DIST} on http://${HOST}:${PORT} (API proxy /api -> ${UPSTREAM.origin})`);
  });

  const stop = () => {
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 5_000).unref();
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}

main();
