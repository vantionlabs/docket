import { migrate, migrationFiles } from "@/Migrations.js";
import { describe, expect, it } from "vitest";

const testDbUrl = () => process.env["TEST_DB_URL"];

/**
 * The property the whole arrangement rests on.
 *
 * There is no ledger and no `schema_migrations` table, so nothing records which
 * migrations have run. That is only safe because every one of them is
 * idempotent — and until now nothing checked. A migration that quietly is not
 * would pass review, pass its first deploy, and fail on the next run of a script
 * somebody trusted, or on the next test container that reuses a database.
 *
 * Applying the whole set twice is the entire test. If it survives that, the
 * "just run them all" contract holds; if it does not, the second run throws with
 * the offending statement.
 */
describe.skipIf(testDbUrl() === undefined)("migrations", () => {
  it("are ordered by filename", async () => {
    const files = await migrationFiles();

    expect(files.length).toBeGreaterThan(0);
    expect([...files]).toEqual([...files].sort());
    // Applying them out of order would fail on a foreign key, so the numeric
    // prefix is load-bearing rather than decorative.
    expect(files.every((file) => /^\d{4}_/.test(file))).toBe(true);
  });

  it("can be applied twice over", async () => {
    const url = testDbUrl()!;

    const first = await migrate(url);
    const second = await migrate(url);

    expect(second).toEqual(first);
  });
});
