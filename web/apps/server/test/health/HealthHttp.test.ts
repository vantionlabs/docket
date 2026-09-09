import { HealthHttp } from "@/health/HealthHttp.js";
import { PgTest, testDbUrl } from "@forge/database/PgTest";
import { Effect, Layer } from "effect";
import { HttpRouter } from "effect/unstable/http";
import { SqlClient } from "effect/unstable/sql";
import { afterAll, describe, expect, it } from "vitest";

/**
 * `provideRequest`, not `provide`. A route's requirements are tagged as
 * per-request, so the dependency has to be supplied into each request's context
 * rather than to the layer — which is what `serve` does for the real server.
 */
const handlerFor = (deps: Layer.Layer<SqlClient.SqlClient>) =>
  HttpRouter.toWebHandler(HealthHttp.pipe(HttpRouter.provideRequest(deps)), {
    disableLogger: true,
  });

/**
 * A client that fails the way an unreachable database does.
 *
 * `sql` is invoked as a template tag, so the proxy needs an `apply` trap as well
 * as `get` — without it the call throws a TypeError and the route returns 500,
 * which would pass a test looking only for "not 200" while proving nothing.
 */
const refuse = () => Effect.fail(new Error("connection refused"));

const Unreachable = Layer.succeed(SqlClient.SqlClient)(
  new Proxy(function() {} as unknown as SqlClient.SqlClient, {
    apply: refuse,
    get: () => refuse,
  }),
);

/**
 * Liveness and readiness answer different questions, and the split only earns
 * its keep if they can disagree.
 *
 * If a database outage failed liveness too, an orchestrator would kill and
 * restart every instance of an application that is running perfectly well and
 * would recover on its own the moment the database came back.
 */
describe("health endpoints", () => {
  const live = handlerFor(Unreachable);
  afterAll(() => live.dispose());

  it("liveness answers 200 even with no database", async () => {
    const response = await live.handler(new Request("http://localhost/health"));

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
  });

  it("readiness answers 503 when the database is unreachable", async () => {
    const response = await live.handler(new Request("http://localhost/ready"));

    // 503, not 500: take this instance out of rotation, do not declare it broken.
    expect(response.status).toBe(503);
  });
});

describe.skipIf(testDbUrl() === undefined)("health endpoints, database reachable", () => {
  const live = handlerFor(PgTest);
  afterAll(() => live.dispose());

  it("readiness answers 200", async () => {
    const response = await live.handler(new Request("http://localhost/ready"));

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ready");
  });
});
