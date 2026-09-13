import path from "node:path";
import { defineConfig, type UserConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { visualEdits } from "@emergentbase/visual-edits/vite";

// Supervisor exports DISABLE_HOT_RELOAD=true when the platform sets ENABLE_RELOAD=false.
const hotReloadDisabled = process.env.DISABLE_HOT_RELOAD === "true";

// Visual Edits (x-* JSX tagging, overlay, /edit-file endpoint) is dev-server-only by
// default (apply: serve); escape hatch mirrors DISABLE_HOT_RELOAD.
const visualEditsDisabled = process.env.DISABLE_VISUAL_EDITS === "true";

// Branded error overlay (build + runtime errors); escape hatch mirrors the two above.
const emergentOverlayDisabled = process.env.DISABLE_EMERGENT_OVERLAY === "true";

// Fails open: a broken overlay package must degrade to "no overlay" (Vite's own overlay
// takes over), never to "no dev server". Never let a preview aid take the app down.
async function loadEmergentOverlay() {
  if (emergentOverlayDisabled) return null;
  try {
    const mod = await import("@emergentbase/overlay/vite");
    return mod.emergentOverlay();
  } catch (e) {
    console.warn("[emergent-overlay] plugin failed to load; using Vite's overlay instead:", e instanceof Error ? e.message : e);
    return null;
  }
}

// Pod inotify quota is node-shared and routinely exhausted; native fs.watch EMFILEs at
// boot. Polling is the load-bearing default (set before Vite evaluates the config).
if (!hotReloadDisabled) {
  process.env.CHOKIDAR_USEPOLLING = "true";
}

// https://vite.dev/config/
export default defineConfig(async () => {
  const emergentOverlay = await loadEmergentOverlay();
  return {
    plugins: [
      react(),
      tailwindcss(),
      ...(visualEditsDisabled ? [] : [visualEdits()]),
      ...(emergentOverlay ? [emergentOverlay] : []),
    ],
    resolve: {
      alias: [
        { find: "@", replacement: path.resolve(__dirname, "./src") },
        // lucide 1.x dropped brand logos; src/lib/lucide-react.tsx restores them on top of the real package.
        { find: /^lucide-react$/, replacement: path.resolve(__dirname, "./src/lib/lucide-react.tsx") },
        { find: "lucide-react-upstream", replacement: path.resolve(__dirname, "./node_modules/lucide-react") },
      ],
    },
    // Every shipped dep, pre-bundled up front. Vite discovers deps lazily, so the first
    // import outside the initial graph would trigger a re-optimize + reload mid-session.
    optimizeDeps: {
      include: [
        "@base-ui/react/button",
        "@base-ui/react/checkbox",
        "@base-ui/react/dialog",
        "@base-ui/react/input",
        "@base-ui/react/menu",
        "@base-ui/react/merge-props",
        "@base-ui/react/popover",
        "@base-ui/react/select",
        "@base-ui/react/tabs",
        "@base-ui/react/use-render",
        "@tanstack/react-query",
        "class-variance-authority",
        "clsx",
        "date-fns",
        "@icons-pack/react-simple-icons",
        "lucide-react-upstream",
        "motion/react",
        "next-themes",
        "react",
        "react-day-picker",
        "react-dom/client",
        "react-is",
        "react-router-dom",
        "recharts",
        "sonner",
        "tailwind-merge",
      ],
      // maplibre-gl ships its geojson/vector worker as a separate ESM chunk that Vite's
      // dep pre-bundling cannot resolve (404 on maplibre-gl-worker.mjs), which silently
      // breaks every GeoJSON source. Serve it unbundled instead.
      exclude: ["maplibre-gl"],
    },
    // MapLibre starts its worker as a module worker (`new Worker(url, { type: "module" })`); the bundled
    // worker (CycloneMap.tsx → `maplibre-gl-worker.mjs?worker&url`) is emitted as an ES module to match.
    worker: { format: "es" },
    server: {
      host: true,
      port: 3000,
      allowedHosts: true,
      // Preview probe + /edit-file are cross-origin from the Emergent tab; Vite defaults to localhost-only CORS.
      cors: true,
      // No hmr.clientPort override: Vite infers the WS target from window.location, which
      // is correct on both localhost:3000 (smoke) and the https/:443 preview proxy.
      // Build-error rendering: emergent-overlay when it loaded, else Vite's own overlay.
      hmr: hotReloadDisabled ? false : { overlay: !emergentOverlay },
      watch: hotReloadDisabled ? null : { usePolling: true, interval: 300 },
      // The /api proxy convention: frontend code calls relative /api/*, never an
      // absolute backend URL. Target is the FastAPI dev server (supervisor: backend).
      proxy: {
        "/api": {
          target: "http://localhost:8001",
          changeOrigin: true,
        },
      },
    },
  } satisfies UserConfig;
});
