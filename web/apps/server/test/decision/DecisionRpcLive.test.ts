import { describe, expect, it } from "@effect/vitest";
import { PgLive } from "@forge/database/PgLive";
import { PgPoolTest, testDbUrl } from "@forge/database/PgTest";
import { DecisionId, DecisionRpcs } from "@forge/domain/decision/DecisionRpc";
import { AuthMiddleware } from "@forge/domain/iam/AuthMiddleware";
import { CurrentUser, Identity, OrgId, UserId } from "@forge/domain/iam/Identity";
import { type Permission, permissionsFor } from "@forge/domain/iam/Permission";
import { DecisionRpcLive } from "@forge/server/decision/DecisionRpcLive";
import { DecisionStore } from "@forge/server/decision/DecisionStore";
import { Effect, Layer } from "effect";
import { RpcTest } from "effect/unstable/rpc";
import { SqlClient } from "effect/unstable/sql";

const owner = Array.from(permissionsFor("owner"));

const as = (org: string, permissions: ReadonlyArray<Permission> = owner) =>
  DecisionRpcLive.pipe(
    Layer.provide(DecisionStore.layer),
    Layer.provideMerge(
      Layer.succeed(AuthMiddleware)(
        AuthMiddleware.of((effect) =>
          Effect.provideService(
            effect,
            CurrentUser,
            new Identity({
              userId: UserId.make(`user_${org}`),
              orgId: OrgId.make(org),
              email: `${org}@example.com`,
              emailVerified: true,
              role: "owner",
              permissions,
            }),
          )
        ),
      ),
    ),
    Layer.provideMerge(PgLive),
    Layer.provideMerge(PgPoolTest),
  );

/** Two organizations, each with one pending decision whose outcome is `approve`. */
const seed = Effect.gen(function*() {
  const sql = yield* SqlClient.SqlClient;

  for (const org of ["org_dec", "org_other"]) {
    yield* sql`insert into "organization" ("id", "name", "slug", "createdAt")
               values (${org}, ${org}, ${org}, now()) on conflict ("id") do nothing`;
    // `reviewedBy` is a real foreign key: a decision can only be signed off by
    // somebody the system knows.
    yield* sql`insert into "user" ("id", "name", "email", "emailVerified")
               values (${`user_${org}`}, ${org}, ${`${org}@example.com`}, true)
               on conflict ("id") do nothing`;
    yield* sql`delete from "decision" where "organizationId" = ${org}`;
    yield* sql`insert into "decision" ("id", "organizationId", "outcome", "rationale")
               values (${`dec_${org}`}, ${org}, 'approve', 'because clause 4.2')`;
  }
});

const statusOf = (id: string) =>
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;
    const rows = yield* sql<{ outcome: string; status: string; overrideOutcome: string | null; }>`
      select "outcome", "status", "overrideOutcome" from "decision" where "id" = ${id}
    `;
    return rows[0];
  });

describe.skipIf(testDbUrl() === undefined)("DecisionRpcLive", () => {
  it.layer(as("org_dec"))("tenant isolation", (it) => {
    /**
     * Deliberately *not* under an unprivileged role: the test database connects
     * as a superuser, which ignores row-level security exactly as a
     * misconfigured `DATABASE_URL` would. What passes here is the explicit
     * `organizationId` filter holding on its own. `OrgScope.test.ts` proves the
     * policy separately.
     */
    it.effect("never returns or opens another organization's decision", () =>
      Effect.gen(function*() {
        const client = yield* RpcTest.makeClient(DecisionRpcs);
        yield* seed;

        const queue = yield* client.ListQueue({ status: null });
        expect(queue.length).toBe(1);
        expect(queue[0]?.id).toBe("dec_org_dec");

        const theirs = yield* client
          .GetDecision({ id: DecisionId.make("dec_org_other") })
          .pipe(Effect.result);
        expect(theirs._tag).toBe("Failure");
      }));
  });

  it.layer(as("org_dec"))("review", (it) => {
    it.effect("approving without an override leaves the pipeline's answer alone", () =>
      Effect.gen(function*() {
        const client = yield* RpcTest.makeClient(DecisionRpcs);
        yield* seed;

        yield* client.ApproveDecision({
          id: DecisionId.make("dec_org_dec"),
          overrideOutcome: null,
          note: null,
        });

        const row = yield* statusOf("dec_org_dec");
        expect(row?.status).toBe("approved");
        expect(row?.outcome).toBe("approve");
        // Agreement is the absence of an override, which is what keeps the
        // override rate meaningful.
        expect(row?.overrideOutcome).toBe(null);
      }));

    it.effect("an override sits beside the original rather than replacing it", () =>
      Effect.gen(function*() {
        const client = yield* RpcTest.makeClient(DecisionRpcs);
        yield* seed;

        yield* client.ApproveDecision({
          id: DecisionId.make("dec_org_dec"),
          overrideOutcome: "route_to_cost_centre",
          note: "over the delegated limit",
        });

        const row = yield* statusOf("dec_org_dec");
        expect(row?.outcome).toBe("approve");
        expect(row?.overrideOutcome).toBe("route_to_cost_centre");

        const decision = yield* client.GetDecision({ id: DecisionId.make("dec_org_dec") });
        expect(decision.effectiveOutcome).toBe("route_to_cost_centre");
      }));

    it.effect("rejecting records the refusal as the reviewer's own outcome", () =>
      Effect.gen(function*() {
        const client = yield* RpcTest.makeClient(DecisionRpcs);
        yield* seed;

        yield* client.RejectDecision({ id: DecisionId.make("dec_org_dec"), note: null });

        const row = yield* statusOf("dec_org_dec");
        expect(row?.status).toBe("rejected");
        expect(row?.outcome).toBe("approve");
        expect(row?.overrideOutcome).toBe("reject");
      }));
  });

  it.layer(as("org_dec", owner.filter((held) => held !== "decision:edit")))(
    "overruling is a separate capability",
    (it) => {
      it.effect("approve alone waves a decision through but cannot overrule it", () =>
        Effect.gen(function*() {
          const client = yield* RpcTest.makeClient(DecisionRpcs);
          yield* seed;

          const overruled = yield* client
            .ApproveDecision({
              id: DecisionId.make("dec_org_dec"),
              overrideOutcome: "reject",
              note: null,
            })
            .pipe(Effect.result);
          expect(overruled._tag).toBe("Failure");

          // The same caller may still agree with the pipeline.
          yield* client.ApproveDecision({
            id: DecisionId.make("dec_org_dec"),
            overrideOutcome: null,
            note: null,
          });
          expect((yield* statusOf("dec_org_dec"))?.status).toBe("approved");
        }));
    },
  );
});
