import { Effect, Layer, Schema } from "effect";
import { SqlClient } from "effect/unstable/sql";
import * as Pg from "pg";
import { PgLive } from "./PgLive.js";
import { PgPool } from "./PgPool.js";

/**
 * Set by `test/global-setup.ts`, which starts one container for the whole run.
 */
export const testDbUrl = () => process.env["TEST_DB_URL"];

/**
 * The shared pool, pointed at the test database. Everything above it — the
 * `SqlClient` and better-auth alike — is the production wiring, so tests
 * exercise the same composition.
 */
export const PgPoolTest: Layer.Layer<PgPool> = Layer.effect(PgPool)(
  Effect.gen(function*() {
    const url = testDbUrl();
    if (url === undefined) {
      throw new Error(
        "TEST_DB_URL is not set. Ensure globalSetup is configured in vitest.config.ts and Docker is running.",
      );
    }

    const pool = new Pg.Pool({ connectionString: url, application_name: "forge-test" });
    pool.on("error", () => {});

    yield* Effect.acquireRelease(
      Effect.promise(() => pool.query("SELECT 1")),
      () => Effect.promise(() => pool.end()).pipe(Effect.ignore),
    );

    return pool;
  }),
).pipe(Layer.orDie);

export const PgTest = PgLive.pipe(Layer.provide(PgPoolTest));

class TransactionRollback extends Schema.TaggedError<TransactionRollback>()("TransactionRollback", {
  value: Schema.Any,
}) {}

/**
 * Runs `self` inside a transaction that is always rolled back, so tests share
 * one database without leaking state into each other.
 */
export const withTransactionRollback = <A, E, R>(self: Effect.Effect<A, E, R>) =>
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;

    return yield* sql
      .withTransaction(
        Effect.gen(function*() {
          const value = yield* self;
          return yield* new TransactionRollback({ value });
        }),
      )
      .pipe(
        Effect.catchIf(Schema.is(TransactionRollback), (error) => Effect.succeed(error.value as A)),
      );
  });
