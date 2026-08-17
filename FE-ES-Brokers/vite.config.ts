// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  // Production builds must target a plain Node server (Replit deployments run
  // `node .output/server/index.mjs`), not the default Cloudflare preset.
  nitro: { preset: "node-server" },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    server: {
      // Allow all hosts so the Replit preview proxy (and nip.io) work without
      // DNS-rebinding false-positives. Fine for a dev server.
      allowedHosts: true,
      // Proxy /api calls to the local FastAPI backend so the browser never needs
      // to reach a different origin — avoids CORS and port-routing complexity in
      // the Replit proxied environment.
      proxy: {
        "/api": {
          target: "http://localhost:4000",
          changeOrigin: true,
        },
      },
    },
  },
});
