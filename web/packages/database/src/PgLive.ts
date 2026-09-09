import { PgClient } from "@effect/sql-pg";
import { Effect, Layer, String } from "effect";
import type { SqlClient } from "effect/unstable/sql";
import { PgPool } from "./PgPool.js";

/**
 * Client-level options shared by the live and test layers, so tests exercise the
 * same identifier casing as production. Pool-level settings live on `PgPool`.
 */
export const pgClientConfig = {
  transformQueryNames: String.camelToSnake,
  transformResultNames: String.snakeToCamel,
} as const;

/**
 * `SqlClient` built on the shared pool rather than one of its own.
 *
 * Connection failures surface as defects at `PgPool`, so nothing actionable
 * remains in the error channel here.
 */
export const PgLive: Layer.Layer<PgClient.PgClient | SqlClient.SqlClient, never, PgPool> = PgClient
  .layerFrom(
    Effect.gen(function*() {
      const pool = yield* PgPool;

      return yield* PgClient.fromPool({
        acquire: Effect.succeed(pool),
        ...pgClientConfig,
      });
    }),
  ).pipe(Layer.orDie);
