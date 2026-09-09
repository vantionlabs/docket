import { describe, expect, it } from "@effect/vitest";
import { PgLive } from "@forge/database/PgLive";
import { PgPoolTest, testDbUrl } from "@forge/database/PgTest";
import { PermissionResolver } from "@forge/server/iam/PermissionResolver";
import { Effect, Layer } from "effect";
import { SqlClient } from "effect/unstable/sql";

const TestLayer = PermissionResolver.layer.pipe(
  Layer.provideMerge(PgLive),
  Layer.provideMerge(PgPoolTest),
);

const seed = Effect.fnUntraced(function*(role: string) {
  const sql = yield* SqlClient.SqlClient;

  yield* sql`insert into "organization" ("id", "name", "slug", "createdAt")
             values ('org_perm', 'Perm', 'perm', now()) on conflict ("id") do nothing`;
  yield* sql`insert into "user" ("id", "name", "email", "emailVerified", "createdAt", "updatedAt")
             values ('user_perm', 'Perm', 'perm@example.com', false, now(), now())
             on conflict ("id") do nothing`;
  yield* sql`insert into "member" ("id", "organizationId", "userId", "role", "createdAt")
             values ('member_perm', 'org_perm', 'user_perm', ${role}, now())
             on conflict ("id") do update set "role" = ${role}`;
});

const cleanup = Effect.fnUntraced(function*() {
  const sql = yield* SqlClient.SqlClient;

  yield* sql`delete from "organizationRole" where "organizationId" = 'org_perm'`;
  yield* sql`delete from "memberPermission" where "organizationId" = 'org_perm'`;
  yield* sql`delete from "organization" where "id" = 'org_perm'`;
  yield* sql`delete from "user" where "id" = 'user_perm'`;
});

describe.skipIf(testDbUrl() === undefined)("PermissionResolver", () => {
  it.layer(TestLayer)("against a real database", (it) => {
    it.effect("reads a custom role out of organizationRole", () =>
      Effect.gen(function*() {
        const sql = yield* SqlClient.SqlClient;
        const resolver = yield* PermissionResolver;

        yield* seed("editor");
        yield* sql`insert into "organizationRole" ("id", "organizationId", "role", "permission", "createdAt")
                   values ('role_editor', 'org_perm', 'editor', ${
          JSON.stringify({ contact: ["read", "update"] })
        }, now())`;

        const permissions = yield* resolver.resolve({
          organizationId: "org_perm",
          memberId: "member_perm",
          role: "editor",
        });

        expect([...permissions].sort()).toEqual(["contact:read", "contact:update"]);

        yield* cleanup();
      }));

    it.effect("applies a per-member revoke over the role", () =>
      Effect.gen(function*() {
        const sql = yield* SqlClient.SqlClient;
        const resolver = yield* PermissionResolver;

        yield* seed("admin");
        yield* sql`insert into "memberPermission" ("id", "organizationId", "memberId", "permission", "granted")
                   values ('mp_1', 'org_perm', 'member_perm', 'member:delete', false)`;

        const permissions = yield* resolver.resolve({
          organizationId: "org_perm",
          memberId: "member_perm",
          role: "admin",
        });

        expect(permissions).not.toContain("member:delete");
        expect(permissions).toContain("member:create");

        yield* cleanup();
      }));
  });
});
