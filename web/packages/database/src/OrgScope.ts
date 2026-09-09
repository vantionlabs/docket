import { CurrentUser } from "@forge/domain/iam/Identity";
import { Effect } from "effect";
import { SqlClient } from "effect/unstable/sql";

/**
 * Runs `self` in a transaction whose `app.current_org` is the caller's org, so
 * the row-level security policies apply.
 *
 * The org is read from `CurrentUser` rather than taken as an argument — a
 * caller can therefore never name a tenant that is not their own. `SET LOCAL`
 * scopes the setting to the transaction, so a pooled connection cannot leak it
 * into the next request.
 */
export const withOrgScope = <A, E, R>(self: Effect.Effect<A, E, R>) =>
  Effect.gen(function*() {
    const identity = yield* CurrentUser;

    return yield* withOrgScopeFor(identity.orgId, self);
  });

/**
 * The same scope, for code that has no caller to read the org from.
 *
 * Request handlers must keep using `withOrgScope`, so that the organization can
 * never be an argument a client controls. This exists for the cases that run
 * outside a request — a background pass over one tenant, or a handler that has
 * just resolved a credential and knows the org before it has an identity.
 */
export const withOrgScopeFor = <A, E, R>(orgId: string, self: Effect.Effect<A, E, R>) =>
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;

    return yield* sql.withTransaction(
      Effect.gen(function*() {
        yield* sql`select set_config('app.current_org', ${orgId}, true)`;

        return yield* self;
      }),
    );
  });

/**
 * Runs `self` able to read across every tenant.
 *
 * Authenticating an API key is the case this exists for: the key is looked up
 * by hash, and which organization it belongs to is the *answer*, not something
 * known going in. That is unavoidably a cross-tenant read.
 *
 * Every policy that honours this setting widens only `using` and never
 * `with check`, so a statement running here can still write nothing outside a
 * properly scoped organization. Keep the body as small as possible — ideally a
 * single select — and prefer handing the org straight to `withOrgScopeFor` once
 * it is known.
 */
export const withWorkerScope = <A, E, R>(self: Effect.Effect<A, E, R>) =>
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;

    return yield* sql.withTransaction(
      Effect.gen(function*() {
        yield* sql`select set_config('app.worker', 'on', true)`;

        return yield* self;
      }),
    );
  });
