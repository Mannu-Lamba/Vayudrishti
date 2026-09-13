// VayuDrishti model test bench — a localhost page that runs all three trained models through the REAL
// FastAPI backend on held-out samples. This server only serves the page, the sample images, the models'
// test reports and fonts, and forwards /api/* to FastAPI (same origin, so no CORS). No model runs here.
//
//   node tests/model-bench/server.mjs            → http://localhost:3001
//   PORT=3002 BACKEND_URL=http://127.0.0.1:8001 node tests/model-bench/server.mjs
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const PORT = Number(process.env.PORT ?? 3001);
const BACKEND = new URL(process.env.BACKEND_URL ?? "http://127.0.0.1:8001");

const TYPES = {
  ".html": "text/html; charset=utf-8", ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg",
  ".woff2": "font/woff2", ".mjs": "text/javascript", ".js": "text/javascript", ".css": "text/css",
};
const FILES = {
  "/": path.join(HERE, "index.html"),
  "/samples.json": path.join(HERE, "samples.json"),
  "/evaluation": path.join(HERE, "evaluation.html"),
  "/evaluation.json": path.join(HERE, "evaluation.json"),  // written by evaluate.py
  "/reports/identification.json": path.join(REPO, "identification_model/reports/test_metrics.json"),
  "/reports/classification.json": path.join(REPO, "identification_model/reports/classification/classification_metrics.json"),
  "/reports/prediction.json": path.join(REPO, "prediction_model/reports/test_metrics.json"),
};
// Only these directories are reachable; anything outside them is a 404.
const MOUNTS = {
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
  try { pathname = decodeURIComponent(new URL(req.url ?? "/", "http://bench").pathname); } catch { return notFound(res); }
  if (pathname.startsWith("/api/")) return proxy(req, res);
  if (FILES[pathname]) return sendFile(res, FILES[pathname]);
  for (const [prefix, dir] of Object.entries(MOUNTS)) {
    if (!pathname.startsWith(prefix)) continue;
    const file = path.resolve(dir, pathname.slice(prefix.length));
    return file.startsWith(dir + path.sep) ? sendFile(res, file) : notFound(res);
  }
  notFound(res);
}).listen(PORT, "127.0.0.1", () => console.log(`Model test bench: http://localhost:${PORT}  (API -> ${BACKEND.origin})`));
