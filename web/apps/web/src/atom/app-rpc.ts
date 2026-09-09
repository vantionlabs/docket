import { AppRpcs } from "@forge/domain/AppRpcs";
import { Layer } from "effect";
import { FetchHttpClient } from "effect/unstable/http";
import { AtomRpc } from "effect/unstable/reactivity";
import { RpcClient, RpcSerialization } from "effect/unstable/rpc";

/**
 * The application's one RPC client, and the one atom runtime behind it.
 *
 * `AtomRpc.Service` builds the flattened client, owns a runtime, and generates
 * `query` and `mutation` atoms from the group — so a read is declared by naming
 * the RPC rather than by hand-writing a service, a runtime and an effect for it.
 *
 * Replacing five of those with one is the point: every atom module previously
 * built its own `Atom.runtime`, and a runtime is a layer build, an RPC client
 * and an HTTP client each.
 */
export class AppRpc extends AtomRpc.Service<AppRpc>()("AppRpc", {
  group: AppRpcs,
  /**
   * The API's own address, not a path on this origin. Every RPC is served by
   * `apps/server`, the same place the auth routes live.
   */
  protocol: RpcClient.layerProtocolHttp({
    url: `${import.meta.env.VITE_AUTH_BASE_URL ?? "http://localhost:3000"}/rpc`,
  }).pipe(
    Layer.provide(RpcSerialization.layerNdjson),
    Layer.provide(FetchHttpClient.layer),
    /**
     * `credentials` because every RPC is authenticated by the session cookie and
     * `fetch` omits cookies on a cross-origin request unless asked. Without it
     * each call arrives anonymous and `AuthMiddleware` refuses it.
     */
    Layer.provide(Layer.succeed(FetchHttpClient.RequestInit)({ credentials: "include" })),
  ),
}) {}
