import { withOrgScope } from "@forge/database/OrgScope";
import { Contact, ContactId } from "@forge/domain/contact/ContactRpc";
import { CurrentUser } from "@forge/domain/iam/Identity";
import { Forbidden, permission, withPolicy } from "@forge/domain/iam/Policy";
import { Context, Effect, Layer } from "effect";
import { SqlClient } from "effect/unstable/sql";
import { randomUUID } from "node:crypto";

/**
 * Contact reads and writes, shared by both transports.
 *
 * The RPC group is our own client's wire: ndjson, one path, tag-dispatched. The
 * public HTTP API is somebody else's. Neither is a good reason to have two
 * implementations of "create a contact" — so the policy check, the org scoping
 * and the SQL live here once, and each transport only maps the result into its
 * own shape.
 *
 * Every statement carries an explicit `organizationId` filter *and* runs inside
 * `withOrgScope`, so tenant isolation holds even where row-level security does
 * not apply — a superuser, or any role with BYPASSRLS, ignores the policy
 * entirely.
 */
export interface ContactStoreService {
  readonly list: Effect.Effect<ReadonlyArray<Contact>, Forbidden, CurrentUser>;
  readonly create: (input: {
    readonly email: string;
    readonly fullName: string;
  }) => Effect.Effect<Contact, Forbidden, CurrentUser>;
  /**
   * Reports whether a row was actually removed, so a caller that has promised
   * its own users a 404 can tell the difference. The RPC transport ignores it —
   * the UI has already removed the row optimistically either way.
   */
  readonly remove: (id: ContactId) => Effect.Effect<boolean, Forbidden, CurrentUser>;
}

export class ContactStore extends Context.Service<ContactStore, ContactStoreService>()(
  "ContactStore",
) {
  static layer: Layer.Layer<ContactStore, never, SqlClient.SqlClient> = Layer.effect(ContactStore)(
    Effect.gen(function*() {
      const sql = yield* SqlClient.SqlClient;

      return {
        list: Effect.gen(function*() {
          const { orgId } = yield* CurrentUser;

          return yield* withOrgScope(
            sql<{ id: string; email: string; fullName: string; }>`
              select "id", "email", "fullName" from "contact"
              where "organizationId" = ${orgId}
              order by "createdAt" desc
            `,
          );
        }).pipe(
          Effect.orDie,
          Effect.map((rows) =>
            rows.map((row) => new Contact({ ...row, id: ContactId.make(row.id) }))
          ),
          withPolicy(permission("contact:read")),
          Effect.provideService(SqlClient.SqlClient, sql),
        ),

        create: (input) =>
          Effect.gen(function*() {
            const { orgId } = yield* CurrentUser;
            const id = ContactId.make(randomUUID());

            yield* withOrgScope(sql`
              insert into "contact" ("id", "organizationId", "email", "fullName")
              values (${id}, ${orgId}, ${input.email}, ${input.fullName})
            `).pipe(Effect.orDie);

            return new Contact({ id, email: input.email, fullName: input.fullName });
          }).pipe(
            withPolicy(permission("contact:create")),
            Effect.provideService(SqlClient.SqlClient, sql),
          ),

        remove: (id) =>
          Effect.gen(function*() {
            const { orgId } = yield* CurrentUser;

            const removed = yield* withOrgScope(
              sql<{ id: string; }>`
                delete from "contact"
                where "id" = ${id} and "organizationId" = ${orgId}
                returning "id"
              `,
            ).pipe(Effect.orDie);

            return removed.length > 0;
          }).pipe(
            withPolicy(permission("contact:delete")),
            Effect.provideService(SqlClient.SqlClient, sql),
          ),
      };
    }),
  );
}
