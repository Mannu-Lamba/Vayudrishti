// VayuDrishti on one port (default 3001):
//   /              the full website (frontend/dist — build it first), live data only
//   /api/*         forwarded to the FastAPI backend (same origin, so the Google sign-in session cookie works)
//   /bench         model test bench: all three trained models run live on held-out samples, plus uploads
//   /evaluation    full held-out test-set evaluation (evaluation.json, written by evaluate.py)
// No model runs here and nothing is mocked; this server only serves files and forwards /api.
//
//   cd frontend && npx vite build          (once, and after frontend changes)
//   node tests/model-bench/server.mjs      → http://localhost:3001
//   PORT=3002 BACKEND_URL=http://127.0.0.1:8001 node tests/model-bench/server.mjs
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const DIST = path.join(REPO, "frontend/dist");
const PORT = Number(process.env.PORT ?? 3001);
const BACKEND = new URL(process.env.BACKEND_URL ?? "http://127.0.0.1:8001");

const TYPES = {
  ".html": "text/html; charset=utf-8", ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
  ".woff2": "font/woff2", ".woff": "font/woff", ".mjs": "text/javascript", ".js": "text/javascript", ".css": "text/css", ".ico": "image/x-icon",
};
const FILES = {
  "/bench": path.join(HERE, "index.html"),
  "/samples.json": path.join(HERE, "samples.json"),
  "/evaluation": path.join(HERE, "evaluation.html"),
  "/evaluation.json": path.join(HERE, "evaluation.json"),
  "/reports/identification.json": path.join(REPO, "identification_model/reports/test_metrics.json"),
  "/reports/classification.json": path.join(REPO, "identification_model/reports/classification/classification_metrics.json"),
  "/reports/prediction.json": path.join(REPO, "prediction_model/reports/test_metrics.json"),
};
// Only these directories are reachable; anything outside them is a 404.
const MOUNTS = {
  "/assets/": path.join(DIST, "assets"),
  "/img/": path.join(REPO, "identification_model/data/processed"),
  "/fonts/sans/": path.join(REPO, "frontend/node_modules/@fontsource/ibm-plex-sans/files"),
  "/fonts/mono/": path.join(REPO, "frontend/node_modules/@fontsource/ibm-plex-mono/files"),
  "/vendor/maplibre/": path.join(REPO, "frontend/node_modules/maplibre-gl/dist"),
};

function notFound(res) {
  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("not found");
}

function sendFile(res, file) {
  fs.stat(file, (error, info) => {
    if (error || !info.isFile()) return notFound(res);
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store" });
    fs.createReadStream(file).pipe(res);
  });
}

function proxy(req, res) {
  const upstream = http.request(
    { hostname: BACKEND.hostname, port: BACKEND.port, path: req.url, method: req.method, headers: { ...req.headers, host: BACKEND.host } },
    (answer) => { res.writeHead(answer.statusCode ?? 502, answer.headers); answer.pipe(res); },
  );
  upstream.on("error", () => {
    if (res.headersSent) return res.end();
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ success: false, error: { code: "BACKEND_UNREACHABLE", message: `The FastAPI backend at ${BACKEND.origin} is not running.` } }));
  });
  req.pipe(upstream);
}

http.createServer((req, res) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(req.url ?? "/", "http://vayudrishti").pathname); } catch { return notFound(res); }
  if (pathname.startsWith("/api/")) return proxy(req, res);
  if (FILES[pathname]) return sendFile(res, FILES[pathname]);
  for (const [prefix, dir] of Object.entries(MOUNTS)) {
    if (!pathname.startsWith(prefix)) continue;
    const file = path.resolve(dir, pathname.slice(prefix.length));
    return file.startsWith(dir + path.sep) ? sendFile(res, file) : notFound(res);
  }
  // The website: a file at the dist root (favicon.svg …), else the app shell for its client-side routes.
  if (path.extname(pathname)) {
    const file = path.resolve(DIST, `.${pathname}`);
    return file.startsWith(DIST + path.sep) ? sendFile(res, file) : notFound(res);
  }
  if (req.method === "GET") return sendFile(res, path.join(DIST, "index.html"));
  notFound(res);
}).listen(PORT, "127.0.0.1", () => console.log(`VayuDrishti on http://localhost:${PORT}  (website /, bench /bench, evaluation /evaluation, API -> ${BACKEND.origin})`));
