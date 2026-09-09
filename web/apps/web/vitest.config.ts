import * as path from "node:path";
import { mergeConfig } from "vitest/config";
import shared from "../../vitest.shared.ts";

export default mergeConfig(shared, {
  test: {
    name: "web",
    // Component tests need a DOM; the setup file adds jest-dom matchers.
    environment: "jsdom",
    // Testing Library's `screen` queries the one shared document, so concurrent
    // tests would interleave their renders and query each other's markup. The
    // shared config turns concurrency on; component tests must opt out.
    sequence: { concurrent: false },
    setupFiles: [path.join(import.meta.dirname, "test/setup.ts")],
    alias: {
      "@/": path.join(import.meta.dirname, "src") + "/",
      "@test/": path.join(import.meta.dirname, "test") + "/",
    },
    include: ["test/**/*.test.ts", "test/**/*.test.tsx", "src/**/*.test.tsx"],
  },
});
