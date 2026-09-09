import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import react from "@vitejs/plugin-react";
import { nitro } from "nitro/vite";
import * as path from "node:path";
import { defineConfig, loadEnv } from "vite";

const repoRoot = path.resolve(import.meta.dirname, "../..");

export default defineConfig(({ command, mode }) => {
  /**
   * Everything below is server-side. Nothing here reaches the browser — the app
   * has no client-side environment variables, and if it ever gains one it must
   * be `VITE_`-prefixed, which is the only way Vite exposes a value to the
   * client bundle.
   *
   * `loadEnv` reads the repo-root `.env`, the same file the API reads. Vite's
   * own loading looks inside this package and only surfaces `VITE_` values, so
   * it would find neither of the two below.
   */
  const env = loadEnv(mode, repoRoot, "");

  /**
   * This server's own address. The port comes from `WEB_URL` because the API
   * already needs that value for its trusted origins, and two variables that
   * must agree is one more than necessary.
   */
  const port = Number(
    new URL(process.env["WEB_URL"] ?? env["WEB_URL"] ?? "http://localhost:5173").port || 5173,
  );

  if (command === "serve") {
    /**
     * One variable the dev server needs in its own process, and only there.
     *
     * A deployment does not have this problem: `PORT` is whatever the platform
     * assigned that container. `pnpm dev` is one shell and one `.env` for two
     * servers, so it is sorted out here instead.
     *
     * Nitro's plugin takes `PORT` as the dev server's port, and that variable
     * belongs to the API — so left alone both halves of `pnpm dev` bind the same
     * one and whichever loses is invisible.
     */
    process.env["PORT"] = String(port);
  }

  return {
    plugins: [
      // Must come before react(). It owns the route tree generation that the
      // standalone router plugin used to do, so there is only one of them.
      tanstackStart(),
      /**
       * Turns the Start build into a deployable server.
       *
       * Without it `vite build` emits a fetch handler and stops, and hosting is
       * the application's problem. Nitro wraps that handler and writes
       * `.output/server/index.mjs`, which `node` runs directly.
       */
      nitro(),
      tailwindcss(),
      react(),
    ],
    /**
     * Bundle the server build's dependencies, but only when building.
     *
     * Vite externalises them by default, which is wrong for an image — it means
     * shipping the dependency tree to run one bundle — and right for the dev
     * server, which is why this is conditional rather than always on. Inlining
     * them in dev puts React's CommonJS entry through Vite's ESM module runner,
     * and every server-rendered route dies on `module is not defined`.
     */
    ssr: command === "build" ? { noExternal: true } : {},
    resolve: {
      /**
       * Source, not build output. The workspace packages expose `src` under a
       * `development` condition; Vite compiles TypeScript, so it wants that in
       * both dev and build rather than requiring the packages be built first.
       */
      conditions: ["development"],
      alias: {
        // Mirrors the `@/*` mapping in tsconfig.app.json and vitest.config.ts.
        "@": path.resolve(import.meta.dirname, "./src"),
      },
    },
    server: {
      port,
      // Fail rather than quietly move if the port is taken; a web server on an
      // unexpected port looks exactly like the API being broken.
      strictPort: true,
    },
  };
});
