import { Config, Context, Effect, Layer, Redacted } from "effect";
import * as Pg from "pg";

/**
 * The one `pg` pool for the process.
 *
 * Both the Effect `SqlClient` (via `PgLive`) and better-auth are built on this
 * single pool. Two pools would double the connection count per worker and stop
 * auth writes from joining application transactions.
 */
export class PgPool extends Context.Service<PgPool, Pg.Pool>()("PgPool") {
  static layer: Layer.Layer<PgPool> = Layer.effect(PgPool)(
    Effect.gen(function*() {
      const url = yield* Config.redacted("DATABASE_URL");
      const ssl = yield* Config.boolean("DATABASE_SSL").pipe(Config.withDefault(false));

      const pool = new Pg.Pool({
        connectionString: Redacted.value(url),
        ssl,
        application_name: "forge",
        connectionTimeoutMillis: 10_000,
        idleTimeoutMillis: 10_000,
      });

      // `pg` emits on idle-client failures; without a listener Node treats it as
      // an unhandled error event and tears the process down.
      pool.on("error", () => {});

      // A database we cannot reach at boot is not actionable by any caller, so
      // this is a defect rather than a typed failure.
      yield* Effect.acquireRelease(
        Effect.promise(() => pool.query("SELECT 1")),
        () => Effect.promise(() => pool.end()).pipe(Effect.ignore),
      );

      return pool;
    }),
  ).pipe(Layer.orDie);
}
