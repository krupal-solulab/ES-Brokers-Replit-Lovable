// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    server: {
      // Reached via a public nip.io hostname (broker.57.174.232.34.nip.io) that
      // resolves to this same machine's IP — Vite blocks unrecognized Host
      // headers by default (DNS-rebinding protection). The leading-dot form
      // matches every subdomain under nip.io for this IP, not just "broker".
      allowedHosts: [".57.174.232.34.nip.io"],
    },
  },
});
