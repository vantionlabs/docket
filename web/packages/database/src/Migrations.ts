import * as fs from "node:fs/promises";
import * as path from "node:path";
import { Pool } from "pg";

/**
 * Applying the committed migrations.
 *
 * There is no ledger and no `schema_migrations` table, and that is the whole
 * design: **every migration is idempotent**. Each one guards with
 * `if not exists`, or drops a constraint or policy before creating it. So the
 * answer to "which of these have run?" is "it does not matter", and applying all
 * of them to any database converges it on the committed schema — a fresh test
 * container, a developer's local Postgres, and production alike.
 *
 * The cost of that choice is real and worth stating: a migration that is *not*
 * idempotent will appear to work once and fail on the next run, and nothing here
 * will catch it. Adding one is a review concern, not something this can enforce.
 */

/**
 * Where the `.sql` files live, resolved from this module rather than the caller's
 * working directory — a runner invoked from the repository root and one invoked
 * from inside the package must find the same files.
 *
 * Resolved relative to this module, so the build copies the `.sql` files next
 * to the bundle. Without that the runner finds an empty directory and reports
 * success having applied nothing, which is a worse failure than not starting.
 */
export const migrationsDir = path.join(import.meta.dirname, "migrations");

/** The migration filenames, in the order they must be applied. */
export const migrationFiles = async (): Promise<ReadonlyArray<string>> =>
  (await fs.readdir(migrationsDir)).filter((file) => file.endsWith(".sql")).sort();

/**
 * Applies every migration to the database at `connectionString`, in order.
 *
 * Each file is executed whole rather than split on semicolons, because several of
 * them contain `do $$ ... $$` blocks and dollar-quoted bodies that a naive split
 * would cut in half.
 *
 * Deliberately plain promises rather than Effect: the two callers are a vitest
 * global setup and a command-line script, neither of which has a runtime to
 * borrow, and giving this an Effect signature would mean building one twice for
 * no gain.
 */
export const migrate = async (
  connectionString: string,
  options: { readonly onFile?: ((file: string) => void) | undefined; } = {},
): Promise<ReadonlyArray<string>> => {
  const files = await migrationFiles();
  const pool = new Pool({ connectionString });

  try {
    for (const file of files) {
      options.onFile?.(file);
      await pool.query(await fs.readFile(path.join(migrationsDir, file), "utf8"));
    }
  } finally {
    await pool.end();
  }

  return files;
};
