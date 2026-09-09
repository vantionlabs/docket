import { describe, expect, it } from "@effect/vitest";
import { PgLive } from "@forge/database/PgLive";
import { PgPoolTest, testDbUrl } from "@forge/database/PgTest";
import { ContactRpcs } from "@forge/domain/contact/ContactRpc";
import { AuthMiddleware } from "@forge/domain/iam/AuthMiddleware";
import { CurrentUser, Identity, OrgId, UserId } from "@forge/domain/iam/Identity";
import { permissionsFor } from "@forge/domain/iam/Permission";
import { ContactRpcLive } from "@forge/server/contact/ContactRpcLive";
import { ContactStore } from "@forge/server/contact/ContactStore";
import { Effect, Layer } from "effect";
import { RpcTest } from "effect/unstable/rpc";
import { SqlClient } from "effect/unstable/sql";

const as = (org: string) =>
  ContactRpcLive.pipe(
    Layer.provide(ContactStore.layer),
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
              permissions: Array.from(permissionsFor("owner")),
            }),
          )
        ),
      ),
    ),
    Layer.provideMerge(PgLive),
    Layer.provideMerge(PgPoolTest),
  );

describe.skipIf(testDbUrl() === undefined)("ContactRpcLive", () => {
  it.layer(as("org_mine"))("tenant isolation", (it) => {
    /**
     * This is a regression test for a leak found in the running app.
     *
     * The handlers originally relied on row-level security alone. The test
     * database connects as a superuser — which ignores RLS entirely, exactly as
     * a misconfigured `DATABASE_URL` would — so another tenant's contacts were
     * counted on the dashboard. Running here *without* assuming an unprivileged
     * role is deliberate: it proves the explicit `organizationId` filters hold
     * on their own.
     */
    it.effect("never returns or counts another organization's contacts", () =>
      Effect.gen(function*() {
        const client = yield* RpcTest.makeClient(ContactRpcs);
        const sql = yield* SqlClient.SqlClient;

        for (const org of ["org_mine", "org_theirs"]) {
          yield* sql`insert into "organization" ("id", "name", "slug", "createdAt")
                     values (${org}, ${org}, ${org}, now()) on conflict ("id") do nothing`;
        }
        yield* sql`insert into "contact" ("id", "organizationId", "email", "fullName")
                   values ('c_theirs', 'org_theirs', 'them@example.com', 'Theirs')
                   on conflict ("id") do nothing`;

        yield* client.CreateContact({ email: "mine@example.com", fullName: "Mine" });

        const listed = yield* client.ListContacts();
        expect(listed.map((contact) => contact.fullName)).toEqual(["Mine"]);

        const overview = yield* client.GetOverview();
        expect(overview.contacts).toBe(1);

        // Naming another tenant's contact must not delete it either.
        yield* client.DeleteContact({ id: listed[0]!.id });
        const survivors = yield* sql`select 1 from "contact" where "id" = 'c_theirs'`;
        expect(survivors).toHaveLength(1);

        yield* sql`delete from "organization" where "id" in ('org_mine', 'org_theirs')`;
      }));
  });
});
