import { NodeHttpServer, NodeRuntime } from "@effect/platform-node";
import { PgLive } from "@forge/database/PgLive";
import { PgPool } from "@forge/database/PgPool";
import { ApiV1 } from "@forge/domain/api/v1/Api";
import { AppRpcs } from "@forge/domain/AppRpcs";
import { Config, Effect, Layer } from "effect";
import { HttpRouter } from "effect/unstable/http";
import { HttpApiBuilder, HttpApiScalar } from "effect/unstable/httpapi";
import { RateLimiter } from "effect/unstable/persistence";
import { RpcSerialization, RpcServer } from "effect/unstable/rpc";
import * as Http from "node:http";
import { ApiKeyAuth } from "./api/ApiKeyAuth.js";
import { ApiV1Live } from "./api/v1/Handlers.js";
import { ContactRpcLive } from "./contact/ContactRpcLive.js";
import { ContactStore } from "./contact/ContactStore.js";
import { Mailer } from "./email/Mailer.js";
import { HealthHttp } from "./health/HealthHttp.js";
import { HealthRpcLive } from "./health/HealthRpcLive.js";
import { AccessRpcLive } from "./iam/AccessRpcLive.js";
import { AuditLog } from "./iam/AuditLog.js";
import { Auth } from "./iam/Auth.js";
import { AuthHttp } from "./iam/AuthHttp.js";
import { AuthMiddlewareLive } from "./iam/AuthMiddlewareLive.js";
import { IamRpcLive } from "./iam/IamRpcLive.js";
import { OrganizationRpcLive } from "./iam/OrganizationRpcLive.js";
import { PermissionResolver } from "./iam/PermissionResolver.js";
import { TelemetryLive } from "./Telemetry.js";

const RpcLive = RpcServer.layer(AppRpcs).pipe(
  Layer.provide(HealthRpcLive),
  Layer.provide(IamRpcLive),
  Layer.provide(OrganizationRpcLive),
  Layer.provide(AccessRpcLive),
  Layer.provide(ContactRpcLive),
  Layer.provide(ContactStore.layer),
  Layer.provide(AuthMiddlewareLive),
  Layer.provide(AuditLog.layer),
  Layer.provide(RpcServer.layerProtocolHttp({ path: "/rpc" })),
  Layer.provide(RpcSerialization.layerNdjson),
);

/**
 * The public API, mounted beside the RPC router rather than inside it.
 *
 * `HttpApiBuilder.layer` also serves the OpenAPI document generated from the
 * same declaration that types the handlers, so the documentation cannot drift
 * from the implementation the way a hand-written one does.
 */
const ApiLive = Layer.mergeAll(
  HttpApiBuilder.layer(ApiV1, { openapiPath: "/api/v1/openapi.json" }),
  HttpApiScalar.layer(ApiV1, { path: "/api/v1/docs" }),
).pipe(Layer.provide(ApiV1Live));

/**
 * The browser talks to this server directly, from the web app's origin.
 *
 * That makes every request cross-origin, so the browser demands CORS before it
 * will send one — and `credentials` because the session cookie is the whole
 * point. `WEB_URL` is the only origin allowed: it is already the trusted origin
 * better-auth checks, so widening this would let a request through that
 * better-auth then refuses anyway.
 */
const CorsLive = Layer.unwrap(
  Effect.gen(function*() {
    const webUrl = yield* Config.nonEmptyString("WEB_URL").pipe(
      Config.withDefault("http://localhost:5173"),
    );

    return HttpRouter.cors({ allowedOrigins: [webUrl], credentials: true });
  }),
);

const Routes = Layer.mergeAll(RpcLive, AuthHttp, HealthHttp, ApiLive, CorsLive);

const HttpLive = Layer.unwrap(
  Effect.gen(function*() {
    const port = yield* Config.port("PORT").pipe(Config.withDefault(3000));

    // `serve` materialises the requirements the route handlers declared, so the
    // application layers are provided here rather than to `Routes`. `PgPool` is
    // provided once for the whole tree, so layer memoisation guarantees the
    // SqlClient and better-auth share a single connection pool.
    return HttpRouter.serve(Routes).pipe(
      Layer.provide(Auth.layer),
      Layer.provide(ApiKeyAuth.layer),
      Layer.provide(ContactStore.layer),
      Layer.provide(PermissionResolver.layer),
      // Swap `layerStoreMemory` for `layerStoreRedis` to share limits across workers.
      Layer.provide(RateLimiter.layer),
      Layer.provide(RateLimiter.layerStoreMemory),
      Layer.provide(PgLive),
      Layer.provide(Mailer.layer),
      Layer.provide(PgPool.layer),
      Layer.provide(NodeHttpServer.layer(() => Http.createServer(), { port })),
    );
  }),
);

/**
 * Telemetry is provided to the running effect rather than into the layer graph.
 *
 * The tracer has to be installed in the context the application *runs in* — a
 * layer nothing names as a dependency is not built, so providing it inside the
 * graph silently did nothing at all.
 */
NodeRuntime.runMain(Layer.launch(HttpLive).pipe(Effect.provide(TelemetryLive)));
