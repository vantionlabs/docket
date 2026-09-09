import { withOrgScope } from "@/OrgScope.js";
import { PgTest, testDbUrl } from "@/PgTest.js";
import { describe, expect, it } from "@effect/vitest";
import { CurrentUser, Identity, OrgId, UserId } from "@forge/domain/iam/Identity";
import { Effect, Layer } from "effect";
import { SqlClient } from "effect/unstable/sql";

const asOrg = (org: string) =>
  Layer.succeed(CurrentUser)(
    new Identity({
      userId: UserId.make("user_rls"),
      orgId: OrgId.make(org),
      email: "rls@example.com",
      emailVerified: true,
      role: "owner",
      permissions: [],
    }),
  );

/**
 * Superusers — and any role with BYPASSRLS — ignore row-level security even
 * when the table is FORCEd. Assuming an unprivileged role inside the outer
 * transaction is what makes this test prove anything; without it the policy
 * would appear to fail open.
 */
const asUnprivilegedRole = (role: string) => <A, E, R>(self: Effect.Effect<A, E, R>) =>
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;

    return yield* sql.withTransaction(
      Effect.gen(function*() {
        // A role name cannot be a bind parameter. These are test constants.
        yield* sql`set local role ${sql.literal(role)}`;

        return yield* self;
      }),
    );
  });

describe.skipIf(testDbUrl() === undefined)("row-level security", () => {
  it.layer(PgTest)("contact isolation", (it) => {
    it.effect("a tenant sees only its own rows, and none unscoped", () =>
      Effect.gen(function*() {
        const sql = yield* SqlClient.SqlClient;

        yield* sql`drop role if exists forge_rls_test`;
        yield* sql`create role forge_rls_test`;
        yield* sql`grant select, insert, update, delete on "contact" to forge_rls_test`;
        yield* sql`grant select on "organization" to forge_rls_test`;

        for (const org of ["org_a", "org_b"]) {
          yield* sql`insert into "organization" ("id", "name", "slug", "createdAt")
                     values (${org}, ${org}, ${org}, now())
                     on conflict ("id") do nothing`;
          yield* sql`insert into "contact" ("id", "organizationId", "email", "fullName")
                     values (${`c_${org}`}, ${org}, ${`${org}@example.com`}, ${org})
                     on conflict ("id") do nothing`;
        }

        const seenByA = yield* asUnprivilegedRole("forge_rls_test")(
          withOrgScope(sql`select "organizationId" from "contact"`).pipe(
            Effect.provide(asOrg("org_a")),
          ),
        );
        expect(seenByA.length).toBe(1);
        expect(seenByA[0]?.["organizationId"]).toBe("org_a");

        const seenByB = yield* asUnprivilegedRole("forge_rls_test")(
          withOrgScope(sql`select "organizationId" from "contact"`).pipe(
            Effect.provide(asOrg("org_b")),
          ),
        );
        expect(seenByB.length).toBe(1);
        expect(seenByB[0]?.["organizationId"]).toBe("org_b");

        // Outside a scoped transaction `app.current_org` is unset, so the policy
        // matches nothing rather than falling open.
        const unscoped = yield* asUnprivilegedRole("forge_rls_test")(
          sql`select "organizationId" from "contact"`,
        );
        expect(unscoped.length).toBe(0);

        yield* sql`delete from "organization" where "id" in ('org_a', 'org_b')`;
        yield* sql`revoke all on "contact" from forge_rls_test`;
        yield* sql`revoke all on "organization" from forge_rls_test`;
        yield* sql`drop role if exists forge_rls_test`;
      }));
  });

  it.layer(PgTest)("decision isolation", (it) => {
    it.effect("a decision and its citations are each isolated on their own", () =>
      Effect.gen(function*() {
        const sql = yield* SqlClient.SqlClient;

        yield* sql`drop role if exists forge_rls_decision`;
        yield* sql`create role forge_rls_decision`;
        yield* sql`grant select, insert, update, delete on "decision" to forge_rls_decision`;
        yield* sql`grant select, insert, update, delete on "decisionCitation" to forge_rls_decision`;
        yield* sql`grant select on "organization" to forge_rls_decision`;

        for (const org of ["org_d1", "org_d2"]) {
          yield* sql`insert into "organization" ("id", "name", "slug", "createdAt")
                     values (${org}, ${org}, ${org}, now())
                     on conflict ("id") do nothing`;
          yield* sql`insert into "decision" ("id", "organizationId", "outcome")
                     values (${`d_${org}`}, ${org}, 'approve')
                     on conflict ("id") do nothing`;
          yield* sql`insert into "decisionCitation"
                       ("id", "organizationId", "decisionId", "citationIndex", "clauseRef", "excerpt")
                     values (${`dc_${org}`}, ${org}, ${`d_${org}`}, 1, '4.2', ${org})
                     on conflict ("id") do nothing`;
        }

        for (const org of ["org_d1", "org_d2"]) {
          const decisions = yield* asUnprivilegedRole("forge_rls_decision")(
            withOrgScope(sql`select "organizationId" from "decision"`).pipe(
              Effect.provide(asOrg(org)),
            ),
          );
          expect(decisions.length).toBe(1);
          expect(decisions[0]?.["organizationId"]).toBe(org);

          // Selected directly rather than through a join, which is the point of
          // the citation carrying its own organization: row-level security
          // filters one table at a time, so a citation reached only through its
          // decision would be isolated by the query rather than by the policy.
          const citations = yield* asUnprivilegedRole("forge_rls_decision")(
            withOrgScope(sql`select "organizationId" from "decisionCitation"`).pipe(
              Effect.provide(asOrg(org)),
            ),
          );
          expect(citations.length).toBe(1);
          expect(citations[0]?.["organizationId"]).toBe(org);
        }

        // Unset `app.current_org` matches nothing rather than falling open.
        const unscoped = yield* asUnprivilegedRole("forge_rls_decision")(
          sql`select "organizationId" from "decision"`,
        );
        expect(unscoped.length).toBe(0);

        yield* sql`delete from "organization" where "id" in ('org_d1', 'org_d2')`;
        yield* sql`revoke all on "decision" from forge_rls_decision`;
        yield* sql`revoke all on "decisionCitation" from forge_rls_decision`;
        yield* sql`revoke all on "organization" from forge_rls_decision`;
        yield* sql`drop role if exists forge_rls_decision`;
      }));
  });
});
