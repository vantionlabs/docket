import * as path from "node:path";
import { defineConfig } from "vite";

/**
 * Bundles the API into one file.
 *
 * Vite rather than a bespoke esbuild script: the web app is already built with
 * it, so this is the same tool and the same shape of config, and it comes with
 * the repository rather than as another dependency.
 *
 * Bundling is an optimisation here, not a workaround. The workspace packages
 * resolve correctly on their own — `tsc` output runs on plain Node — but a
 * bundle only carries the code that is actually reached, which is the
 * difference between a 250MB dependency tree and a 9MB file.
 */
export default defineConfig({
  resolve: {
    // Source, matching the packages' `development` export condition.
    conditions: ["development"],
    alias: {
      // Mirrors the `#src/*` subpath imports in package.json.
      "#src": path.resolve(import.meta.dirname, "./src"),
    },
  },
  ssr: {
    // Bundle the dependencies rather than leaving them to be resolved at
    // runtime; that is the whole point of building this.
    noExternal: true,
    // `pg` reaches for these two only on code paths this never takes: `./native`
    // behind NODE_PG_FORCE_NATIVE, and `pg-cloudflare` in a Workers runtime.
    external: ["pg-native", "pg-cloudflare"],
  },
  build: {
    ssr: "src/Main.ts",
    outDir: "build/bundle",
    target: "node22",
    sourcemap: true,
    rollupOptions: { output: { entryFileNames: "main.js" } },
  },
});
