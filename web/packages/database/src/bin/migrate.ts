import { Redacted } from "effect";
import { migrate } from "../Migrations.js";

/**
 * Applies the migrations to `DATABASE_URL`.
 *
 * A script rather than something the server does at boot. Two servers starting
 * at once would both migrate, and a schema change is the one operation that
 * should happen deliberately and once — not as a side effect of a deploy that
 * might be rolling several instances.
 *
 * `pnpm --filter @forge/database migrate`
 */
const url = process.env["DATABASE_URL"];

if (url === undefined || url === "") {
  console.error("DATABASE_URL is not set.");
  process.exit(1);
}

// Redacted so an accidental log or a crash trace cannot carry the password.
const connectionString = Redacted.make(url);

const applied = await migrate(Redacted.value(connectionString), {
  onFile: (file) => console.log(`  ${file}`),
});

console.log(`Applied ${applied.length} migrations.`);
