import { describe, expect, it } from "@effect/vitest";
import { PgTest, testDbUrl, withTransactionRollback } from "@forge/database/PgTest";
import { HealthRpcs } from "@forge/domain/health/HealthRpc";
import { HealthRpcLive } from "@forge/server/health/HealthRpcLive";
import { Effect, Layer } from "effect";
import { RpcTest } from "effect/unstable/rpc";

// `provideMerge` keeps `SqlClient` in the test context so `withTransactionRollback`
// can reach it, while still feeding it to the handler layer.
const TestLayer = HealthRpcLive.pipe(Layer.provideMerge(PgTest));

describe.skipIf(testDbUrl() === undefined)("HealthRpcLive", () => {
  it.layer(TestLayer)("against a real Postgres", (it) => {
    it.effect("Ping succeeds", () =>
      Effect.gen(function*() {
        const client = yield* RpcTest.makeClient(HealthRpcs);

        expect(yield* client.Ping()).toBeUndefined();
      }));

    it.effect("Check reports a reachable database", () =>
      withTransactionRollback(
        Effect.gen(function*() {
          const client = yield* RpcTest.makeClient(HealthRpcs);

          const report = yield* client.Check();

          expect(report.status).toBe("Ok");
          expect(report.database).toBe(true);
        }),
      ));
  });
});
