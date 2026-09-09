import { Schema } from "effect";

/**
 * Liveness classification for the service as a whole.
 */
export const HealthStatus = Schema.Literals(["Ok", "Degraded"]).annotate({
  identifier: "HealthStatus",
});

export type HealthStatus = typeof HealthStatus.Type;

/**
 * What the server reports when asked how it is doing.
 */
export class HealthReport extends Schema.Class<HealthReport>("HealthReport")({
  status: HealthStatus,
  database: Schema.Boolean,
}) {}

/**
 * The database could not be reached. Actionable: the caller can retry a
 * `ConnectionRefused`, and can back off on a `Timeout`.
 */
export class DatabaseUnreachable extends Schema.TaggedError<DatabaseUnreachable>()(
  "DatabaseUnreachable",
  {
    reason: Schema.Literals(["ConnectionRefused", "Timeout"]),
  },
) {}
