import { describe, expect, it } from "@effect/vitest";
import { DatabaseUnreachable, HealthReport } from "@forge/domain/health/Health";
import { Effect, Schema } from "effect";

describe("HealthReport", () => {
  it.effect("decodes a wire payload", () =>
    Effect.gen(function*() {
      const report = yield* Schema.decodeEffect(HealthReport)({
        status: "Ok",
        database: true,
      });

      expect(report.status).toBe("Ok");
      expect(report.database).toBe(true);
    }));

  it.effect("rejects an unknown status", () =>
    Effect.gen(function*() {
      const result = yield* Effect.result(
        Schema.decodeUnknownEffect(HealthReport)({ status: "Sideways", database: true }),
      );

      expect(result._tag).toBe("Failure");
    }));
});

describe("DatabaseUnreachable", () => {
  it.effect("is yieldable and carries its reason", () =>
    Effect.gen(function*() {
      const error = yield* Effect.flip(new DatabaseUnreachable({ reason: "ConnectionRefused" }));

      expect(error._tag).toBe("DatabaseUnreachable");
      expect(error.reason).toBe("ConnectionRefused");
    }));
});
