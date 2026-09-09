import { PgPool } from "@forge/database/PgPool";
import type { Override, Permission } from "@forge/domain/iam/Permission";
import { resolvePermissions } from "@forge/domain/iam/Permission";
import { Context, Effect, Layer, Schema } from "effect";
import * as Pg from "pg";

/** Shape better-auth stores in `organizationRole.permission`. */
const CustomRoleGrants = Schema.Record(Schema.String, Schema.Array(Schema.String));

const flatten = (grants: Record<string, ReadonlyArray<string>>) =>
  Object.entries(grants).flatMap(([resource, actions]) =>
    actions.map((action) => `${resource}:${action}` as Permission)
  );

export interface PermissionResolverService {
  readonly resolve: (options: {
    readonly organizationId: string;
    readonly memberId: string;
    readonly role: string;
  }) => Effect.Effect<ReadonlyArray<Permission>>;
}

/**
 * Turns a membership into the caller's effective permissions.
 *
 * Reads the same two tables better-auth reads — `organizationRole` for custom
 * roles, plus our `memberPermission` for per-member overrides — so an
 * authorisation decision made here matches one better-auth makes on its own
 * endpoints.
 */
export class PermissionResolver
  extends Context.Service<PermissionResolver, PermissionResolverService>()("PermissionResolver")
{
  static layer: Layer.Layer<PermissionResolver, never, PgPool> = Layer.effect(PermissionResolver)(
    Effect.gen(function*() {
      const pool = yield* PgPool;

      const resolve = (options: {
        readonly organizationId: string;
        readonly memberId: string;
        readonly role: string;
      }) =>
        Effect.promise(async () => {
          const [custom, overrides] = await Promise.all([
            pool.query<{ permission: string; }>(
              `select "permission" from "organizationRole" where "organizationId" = $1 and "role" = $2`,
              [options.organizationId, options.role],
            ),
            pool.query<{ permission: string; granted: boolean; }>(
              `select "permission", "granted" from "memberPermission" where "memberId" = $1`,
              [options.memberId],
            ),
          ]);

          // A custom role with unparseable permissions grants nothing rather
          // than throwing — better-auth logs and rejects, and failing open here
          // would be worse than a caller seeing too little.
          const customRoleGrants = custom.rows.flatMap((row) => {
            const parsed = Schema.decodeUnknownSync(CustomRoleGrants)(JSON.parse(row.permission));

            return flatten(parsed);
          });

          return resolvePermissions({
            role: options.role,
            customRoleGrants,
            overrides: overrides.rows as ReadonlyArray<Override>,
          });
        }).pipe(
          Effect.map((permissions) => Array.from(permissions)),
          // Authorisation must not fail open: if the lookup breaks, the caller
          // gets their role's permissions and nothing more.
          Effect.catchCause(() =>
            Effect.succeed(Array.from(resolvePermissions({
              role: options.role,
              customRoleGrants: [],
              overrides: [],
            })))
          ),
        );

      return { resolve };
    }),
  );
}

export type { Pg };
