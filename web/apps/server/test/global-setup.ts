import { migrate } from "@forge/database/Migrations";
import { PostgreSqlContainer, type StartedPostgreSqlContainer } from "@testcontainers/postgresql";
import { execFileSync } from "node:child_process";

let container: StartedPostgreSqlContainer | undefined;

/**
 * Testcontainers needs a running daemon. Probing keeps `pnpm test` green on
 * machines without Docker — tests that need `TEST_DB_URL` skip instead.
 */
const hasDocker = () => {
  try {
    execFileSync("docker", ["info"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
};

export async function setup() {
  // An externally supplied database wins: it lets a developer without Docker
  // point at a local Postgres, and lets CI reuse a service container.
  if (process.env["TEST_DB_URL"] === undefined) {
    if (!hasDocker()) return;

    container = await new PostgreSqlContainer("postgres:17-alpine").start();
    process.env["TEST_DB_URL"] = container.getConnectionUri();
  }

  // The same runner the `migrate` script uses, so a container and a developer's
  // own database cannot converge on different schemas.
  await migrate(process.env["TEST_DB_URL"]);
}

export async function teardown() {
  await container?.stop();
}
