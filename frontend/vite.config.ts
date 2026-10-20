import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

/** The FastAPI service the development and preview servers forward API calls to. */
const backend = process.env.REFACTOR_AI_BACKEND_URL ?? "http://127.0.0.1:8000";
const proxy = {
  "/api": { target: backend },
  "/health": { target: backend },
};

/**
 * The built page may load scripts, styles and data only from its own origin, so it
 * works offline and cannot fetch anything from the internet. Development keeps Vite's
 * inline hot-reload script, so the policy is added to production builds only.
 */
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self'",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

function contentSecurityPolicy(): Plugin {
  return {
    name: "refactor-ai-content-security-policy",
    apply: "build",
    transformIndexHtml(html) {
      const charset = '<meta charset="UTF-8" />';
      if (!html.includes(charset)) throw new Error("index.html must declare <meta charset=\"UTF-8\" />");
      return html.replace(
        charset,
        `${charset}\n    <meta http-equiv="Content-Security-Policy" content="${CONTENT_SECURITY_POLICY}" />`,
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), contentSecurityPolicy()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    unstubGlobals: true,
    // Dates in assertions are written for UTC, whatever the machine's time zone.
    env: { TZ: "UTC" },
    // The demonstration laptop has 8 GB of RAM shared with model work; a few jsdom
    // workers at a time keep the run reliable.
    maxWorkers: 2,
    testTimeout: 20_000,
  },
});
