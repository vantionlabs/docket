import { withOrgScope } from "@forge/database/OrgScope";
import { ApiKey, CreatedApiKey, hint, KEY_PREFIX } from "@forge/domain/iam/ApiKey";
import { AuditEntry } from "@forge/domain/iam/Audit";
import type { AuditOutcome } from "@forge/domain/iam/Audit";
import { CurrentUser, OrgId } from "@forge/domain/iam/Identity";
import {
  LastOrganization,
  Membership,
  NameMismatch,
  NotAMember,
  OrganizationRpcs,
} from "@forge/domain/iam/OrganizationRpc";
import { permission, withPolicy } from "@forge/domain/iam/Policy";
import { DateTime, Effect } from "effect";
import { SqlClient } from "effect/unstable/sql";
import { createHash, randomBytes, randomUUID } from "node:crypto";

const slugify = (name: string) =>
  `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}-${
    randomUUID().slice(0, 6)
  }`;

export const OrganizationRpcLive = OrganizationRpcs.toLayer(
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;

    return OrganizationRpcs.of({
      // Scoped by membership rather than by the active org, so the switcher can
      // see the organizations the caller is *not* currently in.
      ListMyOrganizations: () =>
        Effect.gen(function*() {
          const identity = yield* CurrentUser;

          const rows = yield* sql<{ orgId: string; name: string; slug: string; role: string; }>`
            select o."id" as "orgId", o."name", o."slug", m."role"
            from "member" m join "organization" o on o."id" = m."organizationId"
            where m."userId" = ${identity.userId}
            order by o."name" asc
          `;

          return rows.map((row) =>
            new Membership({
              orgId: OrgId.make(row.orgId),
              name: row.name,
              slug: row.slug,
              role: row.role,
              isActive: row.orgId === identity.orgId,
            })
          );
        }).pipe(Effect.orDie),

      // Anyone may create an organization — it is their own, and they own it.
      CreateOrganization: Effect.fnUntraced(function*(payload) {
        const identity = yield* CurrentUser;
        const orgId = OrgId.make(randomUUID());
        const slug = slugify(payload.name);

        yield* sql.withTransaction(
          Effect.gen(function*() {
            yield* sql`insert into "organization" ("id", "name", "slug", "createdAt")
                       values (${orgId}, ${payload.name}, ${slug}, now())`;
            yield* sql`insert into "member" ("id", "organizationId", "userId", "role", "createdAt")
                       values (${randomUUID()}, ${orgId}, ${identity.userId}, 'owner', now())`;
            // Land the caller in the organization they just made.
            yield* sql`update "session" set "activeOrganizationId" = ${orgId}
                       where "userId" = ${identity.userId}`;
          }),
        ).pipe(Effect.orDie);

        return new Membership({ orgId, name: payload.name, slug, role: "owner", isActive: true });
      }),

      SwitchOrganization: Effect.fnUntraced(function*(payload) {
        const identity = yield* CurrentUser;

        // Membership is checked before the switch, so naming someone else's
        // organization fails rather than silently pointing the session at it.
        const rows = yield* sql<{ id: string; }>`
          select "id" from "member"
          where "userId" = ${identity.userId} and "organizationId" = ${payload.orgId}
        `.pipe(Effect.orDie);

        if (rows.length === 0) return yield* new NotAMember({ orgId: payload.orgId });

        yield* sql`update "session" set "activeOrganizationId" = ${payload.orgId}
                   where "userId" = ${identity.userId}`.pipe(Effect.orDie);
      }),

      /**
       * Deletes the organization and, by cascade, everything in it.
       *
       * Two things happen first. The caller must have somewhere else to land, or
       * they would be left signed in to nothing; and the name they typed must
       * match, which is what stops a destructive request prepared for one
       * organization from being replayed against another after a switch.
       *
       * Every session pointing at it is moved before the delete, so nobody else
       * in the organization is left holding a session that references a row that
       * no longer exists.
       */
      DeleteOrganization: Effect.fnUntraced(function*(payload) {
        const identity = yield* CurrentUser;

        return yield* Effect.gen(function*() {
          const rows = yield* sql<{ name: string; }>`
            select "name" from "organization" where "id" = ${identity.orgId}
          `.pipe(Effect.orDie);

          const organization = rows[0];
          if (organization === undefined) return;

          if (organization.name !== payload.confirmName) {
            return yield* new NameMismatch({ orgId: identity.orgId });
          }

          const others = yield* sql<{ organizationId: string; }>`
            select "organizationId" from "member"
            where "userId" = ${identity.userId} and "organizationId" <> ${identity.orgId}
            order by "createdAt" asc limit 1
          `.pipe(Effect.orDie);

          const fallback = others[0];
          if (fallback === undefined) {
            return yield* new LastOrganization({ orgId: identity.orgId });
          }

          yield* sql.withTransaction(
            Effect.gen(function*() {
              // Move everybody's session out before the row disappears.
              yield* sql`
                update "session" set "activeOrganizationId" = null
                where "activeOrganizationId" = ${identity.orgId}
              `;
              yield* sql`
                update "session" set "activeOrganizationId" = ${fallback.organizationId}
                where "userId" = ${identity.userId}
              `;
              yield* sql`delete from "organization" where "id" = ${identity.orgId}`;
            }),
          ).pipe(Effect.orDie);
        }).pipe(withPolicy(permission("organization:delete")));
      }),

      ListApiKeys: () =>
        Effect.gen(function*() {
          const identity = yield* CurrentUser;

          const rows = yield* withOrgScope(
            sql<{
              id: string;
              name: string;
              hint: string;
              role: string;
              createdAt: Date;
              lastUsedAt: Date | null;
            }>`
              select "id", "name", "hint", "role", "createdAt", "lastUsedAt"
              from "apiKey"
              where "organizationId" = ${identity.orgId}
              order by "createdAt" desc
            `,
          );

          return rows.map((row) =>
            new ApiKey({
              id: row.id,
              name: row.name,
              hint: row.hint,
              role: row.role,
              createdAt: DateTime.makeUnsafe(row.createdAt),
              lastUsedAt: row.lastUsedAt === null ? null : DateTime.makeUnsafe(row.lastUsedAt),
            })
          );
        }).pipe(Effect.orDie, withPolicy(permission("organization:update"))),

      /**
       * Generated here, never accepted from the client, so a key is always 32
       * bytes of CSPRNG output. Only the hash is stored; the plaintext exists
       * in this response and nowhere else, ever again.
       */
      CreateApiKey: Effect.fnUntraced(function*(payload) {
        const identity = yield* CurrentUser;

        const secret = `${KEY_PREFIX}${randomBytes(32).toString("hex")}`;
        const id = randomUUID();

        yield* withOrgScope(sql`
          insert into "apiKey" ("id", "organizationId", "name", "hash", "hint", "role")
          values (
            ${id}, ${identity.orgId}, ${payload.name},
            ${createHash("sha256").update(secret).digest("hex")},
            ${hint(secret)}, ${payload.role}
          )
        `).pipe(Effect.orDie, withPolicy(permission("organization:update")));

        return new CreatedApiKey({
          key: new ApiKey({
            id,
            name: payload.name,
            hint: hint(secret),
            role: payload.role,
            createdAt: yield* DateTime.now,
            lastUsedAt: null,
          }),
          secret,
        });
      }),

      RevokeApiKey: Effect.fnUntraced(function*(payload) {
        const identity = yield* CurrentUser;

        yield* withOrgScope(sql`
          delete from "apiKey"
          where "id" = ${payload.id} and "organizationId" = ${identity.orgId}
        `).pipe(Effect.orDie, withPolicy(permission("organization:update")));
      }),

      ListAuditLog: Effect.fnUntraced(function*(payload) {
        const identity = yield* CurrentUser;

        const rows = yield* withOrgScope(
          sql<{
            id: string;
            action: string;
            outcome: string;
            actorEmail: string;
            actorRole: string;
            detail: string;
            at: Date;
          }>`
            select "id", "action", "outcome", "actorEmail", "actorRole", "detail", "at"
            from "auditEntry"
            where "organizationId" = ${identity.orgId}
            order by "at" desc
            limit ${payload.limit}
          `,
        ).pipe(
          Effect.orDie,
          // Reading who did what is an administrative capability, not something
          // every member needs.
          withPolicy(permission("member:read")),
        );

        return rows.map((row) =>
          new AuditEntry({
            id: row.id,
            action: row.action,
            // Constrained by `auditEntry_outcome_check`, so the column cannot hold
            // anything else.
            outcome: row.outcome as AuditOutcome,
            actorEmail: row.actorEmail,
            actorRole: row.actorRole,
            detail: row.detail,
            at: DateTime.makeUnsafe(row.at),
          })
        );
      }),

      RenameOrganization: Effect.fnUntraced(function*(payload) {
        const identity = yield* CurrentUser;

        yield* sql`update "organization" set "name" = ${payload.name} where "id" = ${identity.orgId}`
          .pipe(Effect.orDie, withPolicy(permission("organization:update")));
      }),
    });
  }),
);
