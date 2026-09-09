import { withOrgScope } from "@forge/database/OrgScope";
import {
  Citation,
  Decision,
  DecisionId,
  DecisionNotFound,
  type DecisionStatus,
  DecisionSummary,
} from "@forge/domain/decision/DecisionRpc";
import { CurrentUser } from "@forge/domain/iam/Identity";
import { all, Forbidden, permission, withPolicy } from "@forge/domain/iam/Policy";
import { Context, DateTime, Effect, Layer } from "effect";
import { SqlClient } from "effect/unstable/sql";

/**
 * Decision reads and writes, shared by both transports.
 *
 * Follows `ContactStore`: the policy check, the org scoping and the SQL live
 * here once, and each transport only maps the result into its own shape. Every
 * statement carries an explicit `organizationId` filter *and* runs inside
 * `withOrgScope`, so isolation holds even where row-level security does not —
 * a superuser, or any role with BYPASSRLS, ignores the policy entirely.
 */
export interface DecisionStoreService {
  readonly list: (
    status: DecisionStatus | null,
  ) => Effect.Effect<ReadonlyArray<DecisionSummary>, Forbidden, CurrentUser>;
  readonly get: (
    id: DecisionId,
  ) => Effect.Effect<Decision, Forbidden | DecisionNotFound, CurrentUser>;
  readonly approve: (input: {
    readonly id: DecisionId;
    readonly overrideOutcome: string | null;
    readonly note: string | null;
  }) => Effect.Effect<void, Forbidden | DecisionNotFound, CurrentUser>;
  readonly reject: (input: {
    readonly id: DecisionId;
    readonly note: string | null;
  }) => Effect.Effect<void, Forbidden | DecisionNotFound, CurrentUser>;
}

/** The queue's columns. `effectiveOutcome` is derived in SQL so a caller
 * cannot forget the override and read the pipeline's answer as final. */
const summaryColumns = `
  "id", "outcome", coalesce("overrideOutcome", "outcome") as "effectiveOutcome",
  "status", "assignedTo", "groundingPassed", "decidedAt"
`;

interface SummaryRow {
  id: string;
  outcome: string;
  effectiveOutcome: string;
  status: string;
  assignedTo: string | null;
  groundingPassed: boolean;
  decidedAt: Date;
}

/**
 * The fields both shapes share, as a plain object rather than a
 * `DecisionSummary` -- spreading a schema class instance into another
 * constructor works but drops its prototype, so the shared part is built once
 * and each class is constructed from it.
 */
const summaryFields = (row: SummaryRow) => ({
  id: DecisionId.make(row.id),
  outcome: row.outcome,
  effectiveOutcome: row.effectiveOutcome,
  status: row.status as DecisionStatus,
  assignedTo: row.assignedTo,
  groundingPassed: row.groundingPassed,
  decidedAt: DateTime.makeUnsafe(row.decidedAt),
});

const toSummary = (row: SummaryRow) => new DecisionSummary(summaryFields(row));

export class DecisionStore extends Context.Service<DecisionStore, DecisionStoreService>()(
  "DecisionStore",
) {
  static layer: Layer.Layer<DecisionStore, never, SqlClient.SqlClient> = Layer.effect(
    DecisionStore,
  )(
    Effect.gen(function*() {
      const sql = yield* SqlClient.SqlClient;

      return {
        list: (status) =>
          Effect.gen(function*() {
            const { orgId } = yield* CurrentUser;

            // Oldest first: a queue a reviewer works down, not a feed.
            const rows = yield* withOrgScope(
              status === null
                ? sql<SummaryRow>`
                    select ${sql.literal(summaryColumns)} from "decision"
                    where "organizationId" = ${orgId}
                    order by "decidedAt"
                  `
                : sql<SummaryRow>`
                    select ${sql.literal(summaryColumns)} from "decision"
                    where "organizationId" = ${orgId} and "status" = ${status}
                    order by "decidedAt"
                  `,
            );

            return rows.map(toSummary);
          }).pipe(
            Effect.orDie,
            withPolicy(permission("decision:read")),
            Effect.provideService(SqlClient.SqlClient, sql),
          ),

        get: (id) =>
          Effect.gen(function*() {
            const { orgId } = yield* CurrentUser;

            const found = yield* withOrgScope(
              Effect.gen(function*() {
                const rows = yield* sql<
                  SummaryRow & {
                    proposedOutcome: string | null;
                    rationale: string;
                    unmetConditions: ReadonlyArray<string>;
                    railNotes: ReadonlyArray<string>;
                    ruleId: string | null;
                    groundingFailure: string | null;
                    coverageComplete: boolean | null;
                    // `numeric` arrives as a string over the wire protocol, so
                    // it is cast in SQL rather than parsed here.
                    coverageRecall: number | null;
                    reviewedAt: Date | null;
                    overrideOutcome: string | null;
                    overrideNote: string | null;
                  }
                >`
                  select ${sql.literal(summaryColumns)},
                    "proposedOutcome", "rationale", "unmetConditions", "railNotes",
                    "ruleId", "groundingFailure", "coverageComplete",
                    "coverageRecall"::float8 as "coverageRecall",
                    "reviewedAt", "overrideOutcome", "overrideNote"
                  from "decision"
                  where "id" = ${id} and "organizationId" = ${orgId}
                `;

                const row = rows[0];
                if (row === undefined) return null;

                const citations = yield* sql<{
                  id: string;
                  citationIndex: number;
                  clauseRef: string;
                  excerpt: string;
                }>`
                  select "id", "citationIndex", "clauseRef", "excerpt"
                  from "decisionCitation"
                  where "decisionId" = ${id} and "organizationId" = ${orgId}
                  order by "citationIndex"
                `;

                return new Decision({
                  ...summaryFields(row),
                  proposedOutcome: row.proposedOutcome,
                  rationale: row.rationale,
                  unmetConditions: row.unmetConditions,
                  railNotes: row.railNotes,
                  ruleId: row.ruleId,
                  groundingFailure: row.groundingFailure,
                  coverageComplete: row.coverageComplete,
                  coverageRecall: row.coverageRecall,
                  reviewedAt: row.reviewedAt === null ? null : DateTime.makeUnsafe(row.reviewedAt),
                  overrideOutcome: row.overrideOutcome,
                  overrideNote: row.overrideNote,
                  citations: citations.map((citation) => new Citation(citation)),
                });
              }),
            ).pipe(Effect.orDie);

            if (found === null) return yield* new DecisionNotFound({ id });

            return found;
          }).pipe(
            withPolicy(permission("decision:read")),
            Effect.provideService(SqlClient.SqlClient, sql),
          ),

        approve: (input) =>
          Effect.gen(function*() {
            const { orgId, userId } = yield* CurrentUser;

            const updated = yield* withOrgScope(
              sql<{ id: string; }>`
                update "decision"
                set "status" = 'approved',
                    -- Null means the reviewer agreed, so the column keeps
                    -- whatever it held. The pipeline's own "outcome" is never
                    -- touched: the gap between it and the override is the
                    -- override rate.
                    "overrideOutcome" = coalesce(${input.overrideOutcome}, "overrideOutcome"),
                    "overrideNote" = coalesce(${input.note}, "overrideNote"),
                    "reviewedBy" = ${userId},
                    "reviewedAt" = now()
                where "id" = ${input.id} and "organizationId" = ${orgId}
                returning "id"
              `,
            ).pipe(Effect.orDie);

            if (updated.length === 0) return yield* new DecisionNotFound({ id: input.id });
          }).pipe(
            // Overruling the pipeline is a different act from waving it
            // through, and the permission model separates them.
            withPolicy(
              input.overrideOutcome === null
                ? permission("decision:approve")
                : all(permission("decision:approve"), permission("decision:edit")),
            ),
            Effect.provideService(SqlClient.SqlClient, sql),
          ),

        reject: (input) =>
          Effect.gen(function*() {
            const { orgId, userId } = yield* CurrentUser;

            const updated = yield* withOrgScope(
              sql<{ id: string; }>`
                update "decision"
                set "status" = 'rejected',
                    -- Refusing is the one outcome every vertical has, so naming
                    -- it here does not tie the table to invoices.
                    "overrideOutcome" = 'reject',
                    "overrideNote" = coalesce(${input.note}, "overrideNote"),
                    "reviewedBy" = ${userId},
                    "reviewedAt" = now()
                where "id" = ${input.id} and "organizationId" = ${orgId}
                returning "id"
              `,
            ).pipe(Effect.orDie);

            if (updated.length === 0) return yield* new DecisionNotFound({ id: input.id });
          }).pipe(
            withPolicy(permission("decision:reject")),
            Effect.provideService(SqlClient.SqlClient, sql),
          ),
      };
    }),
  );
}
