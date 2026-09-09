import { withOrgScope } from "@forge/database/OrgScope";
import { ContactRpcs, Overview } from "@forge/domain/contact/ContactRpc";
import { CurrentUser } from "@forge/domain/iam/Identity";
import { permission, withPolicy } from "@forge/domain/iam/Policy";
import { Effect } from "effect";
import { SqlClient } from "effect/unstable/sql";
import { ContactStore } from "./ContactStore.js";

/**
 * The RPC transport over the shared store.
 *
 * The list and the writes are the store's; only `GetOverview` is here, because
 * it is a dashboard concern rather than a contact one — it counts members and
 * roles too, and no public API asks for it.
 */
export const ContactRpcLive = ContactRpcs.toLayer(
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;
    const contacts = yield* ContactStore;

    return ContactRpcs.of({
      ListContacts: () => contacts.list,

      CreateContact: (payload) => contacts.create(payload),

      // The flag is for the public API's 404; this transport promises Void.
      DeleteContact: (payload) => contacts.remove(payload.id).pipe(Effect.asVoid),

      GetOverview: () =>
        Effect.gen(function*() {
          const { orgId } = yield* CurrentUser;

          const contactCount = yield* withOrgScope(
            sql<{ count: string; }>`
              select count(*)::text as "count" from "contact" where "organizationId" = ${orgId}
            `,
          );
          const members = yield* sql<{ count: string; }>`
            select count(*)::text as "count" from "member" where "organizationId" = ${orgId}
          `;
          const roles = yield* sql<{ count: string; }>`
            select count(*)::text as "count" from "organizationRole"
            where "organizationId" = ${orgId}
          `;

          return new Overview({
            contacts: Number(contactCount[0]?.count ?? 0),
            members: Number(members[0]?.count ?? 0),
            customRoles: Number(roles[0]?.count ?? 0),
          });
        }).pipe(Effect.orDie, withPolicy(permission("contact:read"))),
    });
  }),
);
