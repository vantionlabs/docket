import { withOrgScopeFor } from "@forge/database/OrgScope";
import { auditableFields } from "@forge/domain/iam/Audit";
import type { AuditOutcome } from "@forge/domain/iam/Audit";
import type { Identity } from "@forge/domain/iam/Identity";
import { Context, Effect, Layer } from "effect";
import { SqlClient } from "effect/unstable/sql";
import { randomUUID } from "node:crypto";

export interface AuditLogService {
  /**
   * Records one action. Never fails.
   *
   * Refusing the work because its audit row would not insert is worse than
   * the missing row, so failures are swallowed here rather than surfaced to the
   * caller — the span carries the cause for anybody looking.
   */
  readonly record: (options: {
    readonly identity: Identity;
    readonly action: string;
    readonly outcome: AuditOutcome;
    readonly payload: unknown;
  }) => Effect.Effect<void>;
}

/**
 * Auditing as a collaborator rather than something the auth middleware does
 * with a database handle it happened to have. It is a service so the middleware
 * can be tested without a database — which is the whole point of that test —
 * and so the writing itself can be tested without an RPC.
 */
export class AuditLog extends Context.Service<AuditLog, AuditLogService>()("AuditLog") {
  static layer: Layer.Layer<AuditLog, never, SqlClient.SqlClient> = Layer.effect(AuditLog)(
    Effect.gen(function*() {
      const sql = yield* SqlClient.SqlClient;

      return {
        record: (options) => {
          const detail = Object.entries(auditableFields(options.payload))
            .map(([key, value]) => `${key}=${value}`)
            .join(" ");

          return withOrgScopeFor(
            options.identity.orgId,
            sql`
              insert into "auditEntry" (
                "id", "organizationId", "actorUserId", "actorEmail", "actorRole",
                "action", "outcome", "detail"
              )
              values (
                ${randomUUID()}, ${options.identity.orgId}, ${options.identity.userId},
                ${options.identity.email}, ${options.identity.role},
                ${options.action}, ${options.outcome}, ${detail}
              )
            `,
          ).pipe(
            // `withOrgScopeFor` takes the client from context; providing it here
            // keeps `record` free of requirements, so a middleware that may only
            // ask for `Scope` can call it.
            Effect.provideService(SqlClient.SqlClient, sql),
            Effect.ignore,
            Effect.withSpan("audit.record"),
          );
        },
      };
    }),
  );

  /** For tests that are not about auditing. Records nothing, fails never. */
  static layerNoop: Layer.Layer<AuditLog> = Layer.succeed(AuditLog)(
    AuditLog.of({ record: () => Effect.void }),
  );
}
