import { Effect, Layer } from "effect";
import { HttpRouter, HttpServerResponse } from "effect/unstable/http";
import { SqlClient } from "effect/unstable/sql";

/**
 * A plain HTTP health check, for things that cannot speak RPC.
 *
 * The `Check` RPC already reports the same thing in more detail, but a load
 * balancer, a container orchestrator and a platform's own probe all want one
 * unauthenticated GET that answers 200 or does not. Making them speak ndjson
 * RPC to find out whether the process is alive is not a trade worth making.
 *
 * Two endpoints, because they answer different questions:
 *
 * `/health` is liveness — the process is up and serving. It touches nothing
 * else, so a database outage does not cause an orchestrator to kill and restart
 * every instance of an application that is running perfectly well and would
 * recover on its own.
 *
 * `/ready` is readiness — this instance can serve traffic, which here means it
 * can reach Postgres. Failing this takes an instance out of rotation without
 * killing it, which is the correct response to a dependency being down.
 */
export const HealthHttp = Layer.mergeAll(
  HttpRouter.add("GET", "/health", HttpServerResponse.text("ok")),
  HttpRouter.add(
    "GET",
    "/ready",
    Effect.gen(function*() {
      const sql = yield* SqlClient.SqlClient;

      return yield* sql`SELECT 1`.pipe(
        Effect.as(HttpServerResponse.text("ready")),
        // 503, not 500: the instance is fine, its dependency is not, and that
        // is the difference between "take me out of rotation" and "I am broken".
        Effect.orElseSucceed(() => HttpServerResponse.text("not ready", { status: 503 })),
      );
    }),
  ),
);
