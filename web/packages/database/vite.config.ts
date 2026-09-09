import { defineConfig } from "vite";

/**
 * Bundles the migration runner into one file.
 *
 * Same tool and same reasoning as the API's bundle next door: the image that
 * ships this carries no node_modules, so the runner has to be self-contained.
 *
 * The `.sql` files are deliberately not bundled. `Migrations.ts` reads them from
 * disk beside itself, which keeps them readable in the image — worth being able
 * to `cat` when a deploy has gone wrong.
 */
export default defineConfig({
  resolve: { conditions: ["development"] },
  ssr: {
    noExternal: true,
    external: ["pg-native", "pg-cloudflare"],
  },
  build: {
    ssr: "src/bin/migrate.ts",
    outDir: "build/bundle",
    target: "node22",
    sourcemap: true,
    rollupOptions: { output: { entryFileNames: "migrate.js" } },
  },
});
