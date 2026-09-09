import { DatabaseUnreachable, HealthReport } from "@forge/domain/health/Health";
import { HealthRpcs } from "@forge/domain/health/HealthRpc";
import { Effect, Layer } from "effect";
import type { Rpc, RpcGroup } from "effect/unstable/rpc";
import { SqlClient, SqlError } from "effect/unstable/sql";

/**
 * Handlers for the health group. The only failure a caller can act on is the
 * database being unreachable — every other `SqlError` reason is a defect.
 */
export const HealthRpcLive: Layer.Layer<
  Rpc.ToHandler<RpcGroup.Rpcs<typeof HealthRpcs>>,
  never,
  SqlClient.SqlClient
> = HealthRpcs
  .toLayer(
    Effect.gen(function*() {
      const sql = yield* SqlClient.SqlClient;

      return HealthRpcs.of({
        Ping: () => Effect.void,

        Check: Effect.fnUntraced(function*() {
          yield* sql`SELECT 1`.pipe(
            Effect.catchTag(
              "SqlError",
              (error: SqlError.SqlError) =>
                new DatabaseUnreachable({
                  reason: error.message.includes("timeout") ? "Timeout" : "ConnectionRefused",
                }),
            ),
          );

          return new HealthReport({ status: "Ok", database: true });
        }),
      });
    }),
  );
