import { describe, expect, it } from "@effect/vitest";
import { HealthClient } from "@forge/web/rpc/health-client";
import { Effect, Layer } from "effect";
import { HttpClient, HttpClientError } from "effect/unstable/http";

/**
 * HTTP is the one true external boundary here, so it is the only layer
 * swapped — serialization, the protocol and the client itself stay production.
 */
const UnreachableTransport = Layer.succeed(HttpClient.HttpClient)(
  HttpClient.make((request) =>
    new HttpClientError.HttpClientError({
      reason: new HttpClientError.TransportError({
        request,
        description: "connection refused",
      }),
    })
  ),
);

const TestLayer = HealthClient.layer("/rpc").pipe(Layer.provide(UnreachableTransport));

describe("HealthClient", () => {
  it.effect("surfaces a transport failure as a typed client error", () =>
    Effect.gen(function*() {
      const client = yield* HealthClient;

      const result = yield* Effect.result(client.Ping());

      expect(result._tag).toBe("Failure");
    }).pipe(Effect.provide(TestLayer)));
});
