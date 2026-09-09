import { withOrgScope } from "@forge/database/OrgScope";
import {
  AccessRpcs,
  CustomRole,
  MemberOverride,
  OrganizationMember,
} from "@forge/domain/iam/AccessRpc";
import { CurrentUser } from "@forge/domain/iam/Identity";
import type { Permission } from "@forge/domain/iam/Permission";
import { fromGrants, toGrants } from "@forge/domain/iam/Permission";
import { permission, withPolicy } from "@forge/domain/iam/Policy";
import { Effect, Schema } from "effect";
import { SqlClient } from "effect/unstable/sql";
import { randomUUID } from "node:crypto";

/** The shape better-auth stores in `organizationRole.permission`. */
const StoredGrants = Schema.Record(Schema.String, Schema.Array(Schema.String));

/**
 * Managing access control.
 *
 * Every statement is scoped by the caller's own `orgId` from `CurrentUser` — no
 * handler takes an organization as a payload, so one organization can never
 * read or rewrite another's roles. `memberPermission` is additionally covered
 * by row-level security through `withOrgScope`.
 */
export const AccessRpcLive = AccessRpcs.toLayer(
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;

    return AccessRpcs.of({
      ListRoles: () =>
        Effect.gen(function*() {
          const { orgId } = yield* CurrentUser;

          const rows = yield* sql<{ role: string; permission: string; }>`
            select "role", "permission" from "organizationRole"
            where "organizationId" = ${orgId} order by "role" asc
          `.pipe(Effect.orDie);

          return rows.map((row) =>
            new CustomRole({
              role: row.role,
              // Anything unparseable is reported as an empty role rather than
              // failing the whole listing.
              permissions: Schema.decodeUnknownOption(StoredGrants)(JSON.parse(row.permission))
                .pipe(
                  (option) => option._tag === "Some" ? fromGrants(option.value) : [],
                ),
            })
          );
        }).pipe(withPolicy(permission("ac:read"))),

      SetRole: Effect.fnUntraced(function*(payload) {
        const { orgId } = yield* CurrentUser;
        const stored = JSON.stringify(toGrants(payload.role.permissions));

        yield* sql.withTransaction(
          Effect.gen(function*() {
            yield* sql`delete from "organizationRole"
                       where "organizationId" = ${orgId} and "role" = ${payload.role.role}`;
            yield* sql`insert into "organizationRole"
                         ("id", "organizationId", "role", "permission", "createdAt")
                       values (${randomUUID()}, ${orgId}, ${payload.role.role}, ${stored}, now())`;
          }),
        ).pipe(Effect.orDie, withPolicy(permission("ac:create")));
      }),

      DeleteRole: Effect.fnUntraced(function*(payload) {
        const { orgId } = yield* CurrentUser;

        yield* sql`delete from "organizationRole"
                   where "organizationId" = ${orgId} and "role" = ${payload.role}`
          .pipe(Effect.orDie, withPolicy(permission("ac:delete")));
      }),

      ListMembers: () =>
        Effect.gen(function*() {
          const { orgId } = yield* CurrentUser;

          const rows = yield* sql<{ memberId: string; email: string; role: string; }>`
            select m."id" as "memberId", u."email" as "email", m."role" as "role"
            from "member" m join "user" u on u."id" = m."userId"
            where m."organizationId" = ${orgId} order by u."email" asc
          `.pipe(Effect.orDie);

          return rows.map((row) => new OrganizationMember(row));
        }).pipe(withPolicy(permission("member:read"))),

      ListMemberOverrides: Effect.fnUntraced(function*(payload) {
        const rows = yield* withOrgScope(sql<{ permission: string; granted: boolean; }>`
          select "permission", "granted" from "memberPermission"
          where "memberId" = ${payload.memberId} order by "permission" asc
        `).pipe(Effect.orDie, withPolicy(permission("ac:read")));

        return rows.map((row) =>
          new MemberOverride({
            memberId: payload.memberId,
            permission: row.permission as Permission,
            granted: row.granted,
          })
        );
      }),

      SetMemberOverride: Effect.fnUntraced(function*(payload) {
        const { orgId } = yield* CurrentUser;
        const { memberId, permission: granted, granted: isGranted } = payload.override;

        yield* withOrgScope(sql`
          insert into "memberPermission"
            ("id", "organizationId", "memberId", "permission", "granted")
          values (${randomUUID()}, ${orgId}, ${memberId}, ${granted}, ${isGranted})
          on conflict ("memberId", "permission")
          do update set "granted" = ${isGranted}
        `).pipe(Effect.orDie, withPolicy(permission("ac:update")));
      }),

      ClearMemberOverride: Effect.fnUntraced(function*(payload) {
        yield* withOrgScope(sql`
          delete from "memberPermission"
          where "memberId" = ${payload.memberId} and "permission" = ${payload.permission}
        `).pipe(Effect.orDie, withPolicy(permission("ac:update")));
      }),
    });
  }),
);
