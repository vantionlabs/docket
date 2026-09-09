import { HealthRpcs } from "@forge/domain/health/HealthRpc";
import { Context, Layer } from "effect";
import { FetchHttpClient, HttpClient } from "effect/unstable/http";
import { RpcClient, RpcGroup, RpcSerialization } from "effect/unstable/rpc";
import type { RpcClientError } from "effect/unstable/rpc/RpcClientError";

/**
 * Browser-side handle on the health group, spoken over ndjson HTTP.
 */
export class HealthClient extends Context.Service<
  HealthClient,
  RpcClient.RpcClient<RpcGroup.Rpcs<typeof HealthRpcs>, RpcClientError>
>()("HealthClient") {
  /**
   * Everything but the transport. `HttpClient` stays open so tests can swap
   * the one true external boundary without faking the RPC layer above it.
   */
  static layer = (url: string): Layer.Layer<HealthClient, never, HttpClient.HttpClient> =>
    Layer.effect(HealthClient)(RpcClient.make(HealthRpcs)).pipe(
      Layer.provide(RpcClient.layerProtocolHttp({ url })),
      Layer.provide(RpcSerialization.layerNdjson),
    );

  static layerFetch = (url: string): Layer.Layer<HealthClient> =>
    HealthClient.layer(url).pipe(Layer.provide(FetchHttpClient.layer));
}
