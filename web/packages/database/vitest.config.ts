import * as path from "node:path";
import { mergeConfig } from "vitest/config";
import shared from "../../vitest.shared.ts";

export default mergeConfig(shared, {
  test: {
    name: "database",
    alias: {
      "@/": path.join(import.meta.dirname, "src") + "/",
      "@test/": path.join(import.meta.dirname, "test") + "/",
    },
    // Serial, and ahead of the server project, because both share one database.
    //
    // The group is 1 rather than 0 so the parallel projects keep the default:
    // Vitest refuses to put two projects in one group when their worker counts
    // differ, and running one worker is what serial means.
    //
    // Within this project the two files actively fight: applying the migrations
    // twice is what Migrations.test.ts is *for*, and migration 0002 drops and
    // recreates the policy that OrgScope.test.ts is asserting isolates tenants.
    // Run concurrently, the drop lands inside the assertion and a tenant sees
    // rows it should not — a failure that reads as a row-level-security bug and
    // is really a scheduling one.
    sequence: { concurrent: false, groupOrder: 1 },
    fileParallelism: false,
  },
});
