import * as path from "node:path";
import { mergeConfig } from "vitest/config";
import shared from "../../vitest.shared.ts";

export default mergeConfig(shared, {
  test: {
    name: "server",
    alias: {
      "@/": path.join(import.meta.dirname, "src") + "/",
      "@test/": path.join(import.meta.dirname, "test") + "/",
    },
    // One Postgres container for the whole run, rather than one per test file.
    globalSetup: [path.join(import.meta.dirname, "test/global-setup.ts")],
    // Serial, because these tests share one database.
    //
    // Several of them truncate a table, write one row and assert on row zero —
    // the audit log tests most obviously. Run concurrently, one file's reset
    // lands between another's write and its read, and the failure looks like a
    // logic bug rather than a scheduling one. `sequence.concurrent` orders tests
    // within a file; `fileParallelism` orders the files.
    //
    // `groupOrder` 2 puts this project after `database`, which applies the
    // migrations twice on purpose — doing that underneath a running server test
    // would contend for locks rather than test anything.
    sequence: { concurrent: false, groupOrder: 2 },
    fileParallelism: false,
  },
});
