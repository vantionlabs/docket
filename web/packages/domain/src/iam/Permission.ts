import { Schema } from "effect";

/**
 * The one permission model, shared by our RPC policies and by better-auth's
 * organization plugin.
 *
 * The resource and action names are better-auth's, not ours: its endpoints
 * check `member:create` before accepting an invite, `organization:delete`
 * before removing an org, and so on. Inventing a parallel vocabulary is what
 * lets two systems quietly disagree about who may do what, so the server builds
 * better-auth's access control from exactly this declaration.
 */
export const statements = {
  organization: ["update", "delete"],
  member: ["read", "create", "update", "delete"],
  invitation: ["create", "cancel"],
  team: ["create", "update", "delete"],
  ac: ["create", "read", "update", "delete"],
  // Ours, unknown to better-auth, governed only by our policies.
  contact: ["read", "create", "update", "delete"],
} as const satisfies Record<string, ReadonlyArray<string>>;

export type Statements = typeof statements;
export type Resource = keyof Statements;

export type InferPermissions<T extends Record<string, ReadonlyArray<string>>> = {
  [K in keyof T]: `${K & string}:${T[K][number]}`;
}[keyof T];

export type Permission = InferPermissions<Statements>;

const flatten = (grants: Grants): ReadonlyArray<Permission> =>
  Object.entries(grants).flatMap(([resource, actions]) =>
    (actions as ReadonlyArray<string>).map((action) => `${resource}:${action}` as Permission)
  );

export const PermissionSchema = Schema.Literals(flatten(statements) as Array<Permission>).annotate({
  identifier: "Permission",
});

/**
 * Roles come from better-auth's organization plugin, so the values must match
 * what it writes to the `member` table.
 */
export const Role = Schema.Literals(["owner", "admin", "member"]).annotate({ identifier: "Role" });
export type Role = typeof Role.Type;

/** A role's grants, in the shape better-auth's `ac.newRole` expects. */
export type Grants = { readonly [K in Resource]?: ReadonlyArray<Statements[K][number]>; };

/**
 * Owner and admin match better-auth's own defaults so its endpoints behave as
 * documented; the only difference is `organization:delete`, which stays with
 * the owner. `contact` is ours to decide.
 */
export const grantsFor: Record<Role, Grants> = {
  owner: {
    organization: ["update", "delete"],
    member: ["read", "create", "update", "delete"],
    invitation: ["create", "cancel"],
    team: ["create", "update", "delete"],
    ac: ["create", "read", "update", "delete"],
    contact: ["read", "create", "update", "delete"],
  },
  admin: {
    organization: ["update"],
    member: ["read", "create", "update", "delete"],
    invitation: ["create", "cancel"],
    team: ["create", "update", "delete"],
    ac: ["create", "read", "update", "delete"],
    contact: ["read", "create", "update", "delete"],
  },
  member: {
    ac: ["read"],
    contact: ["read", "create", "update"],
  },
};

/**
 * Flat permissions to the nested shape better-auth stores in
 * `organizationRole.permission`, and back. The storage format is better-auth's,
 * so these two must stay exact — a mismatch means its endpoints and our
 * policies read different things.
 */
export const toGrants = (permissions: ReadonlyArray<Permission>): Record<string, Array<string>> => {
  const grants: Record<string, Array<string>> = {};

  for (const permission of permissions) {
    const [resource, action] = permission.split(":");
    if (resource === undefined || action === undefined) continue;

    (grants[resource] ??= []).push(action);
  }

  return grants;
};

export const fromGrants = (
  grants: Record<string, ReadonlyArray<string>>,
): ReadonlyArray<Permission> => flatten(grants);

/** Permissions from a built-in role. Unknown (custom) roles start from nothing. */
export const permissionsFor = (role: string): ReadonlySet<Permission> =>
  new Set(isRole(role) ? flatten(grantsFor[role]) : []);

export const isRole = (role: string): role is Role => role in grantsFor;

/** A single member-level adjustment on top of whatever the role grants. */
export interface Override {
  readonly permission: Permission;
  readonly granted: boolean;
}

/**
 * The caller's effective permissions.
 *
 * Applied in order: the role's grants, then any custom-role grants better-auth
 * holds for this organization, then per-member overrides. Revokes are applied
 * last and win, so one capability can be taken from a member without inventing
 * a role for it.
 */
export const resolvePermissions = (options: {
  readonly role: string;
  readonly customRoleGrants: ReadonlyArray<Permission>;
  readonly overrides: ReadonlyArray<Override>;
}): ReadonlySet<Permission> => {
  const resolved = new Set(permissionsFor(options.role));

  for (const granted of options.customRoleGrants) resolved.add(granted);

  for (const override of options.overrides) {
    if (override.granted) resolved.add(override.permission);
    else resolved.delete(override.permission);
  }

  return resolved;
};
