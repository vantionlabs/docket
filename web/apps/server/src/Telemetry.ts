// The subpath, not the barrel: the package index also exports `WebSdk`, which
// imports @opentelemetry/sdk-trace-web — a browser dependency this server has no
// reason to install, and whose absence stops the process booting at all.
import * as NodeSdk from "@effect/opentelemetry/NodeSdk";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { Config, Effect, Option, Redacted } from "effect";

/**
 * Tracing, when somewhere is configured to receive it.
 *
 * `RULES.md` tells contributors not to add manual logging on error paths
 * because "OTEL spans already capture failures and context". That was only true
 * of the spans themselves — nothing exported them, so the context existed and
 * went nowhere. This is the other half.
 *
 * The exporter is installed only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, and
 * off is the honest default for a boilerplate: an exporter pointed at nothing
 * retries on a schedule and fills the log with connection failures.
 *
 * That decision is made by *omitting* `spanProcessor` rather than by returning
 * an empty layer. `NodeSdk.layer` already installs a tracer only when it has a
 * processor, and a branch that returns `Layer.empty` types the whole thing as
 * providing nothing — so nothing depends on it, and it is never built at all.
 *
 * `Effect.withSpan` and `Effect.fn` are what produce the spans; this only
 * decides where they go.
 */
export const TelemetryLive = NodeSdk.layer(
  Effect.gen(function*() {
    const endpoint = yield* Config.option(
      Config.nonEmptyString("OTEL_EXPORTER_OTLP_ENDPOINT"),
    );

    const serviceName = yield* Config.nonEmptyString("OTEL_SERVICE_NAME").pipe(
      Config.withDefault("forge-server"),
    );

    /**
     * Sent as an `Authorization` header when present, which is what every
     * hosted collector wants. Redacted so a crash trace cannot carry the token.
     */
    const headers = yield* Config.option(Config.redacted("OTEL_EXPORTER_OTLP_HEADERS"));

    return {
      resource: { serviceName },
      ...(Option.isNone(endpoint) ? {} : {
        // Batched rather than simple: exporting a span per request synchronously
        // would put the collector on the critical path of every response.
        spanProcessor: new BatchSpanProcessor(
          new OTLPTraceExporter({
            url: `${endpoint.value.replace(/\/$/, "")}/v1/traces`,
            ...(Option.isNone(headers)
              ? {}
              : { headers: { authorization: Redacted.value(headers.value) } }),
          }),
        ),
      }),
    };
  }),
);
