import { Schema } from "effect";
import { Rpc, RpcGroup } from "effect/unstable/rpc";
import { AuthMiddleware } from "./AuthMiddleware.js";
import { PermissionSchema } from "./Permission.js";
import { Forbidden } from "./Policy.js";

/**
 * A role defined by an organization rather than by us.
 *
 * Permissions travel flat (`contact:read`) because that is how the rest of the
 * domain talks about them; the server converts to and from the nested shape
 * better-auth stores.
 */
export class CustomRole extends Schema.Class<CustomRole>("CustomRole")({
  role: Schema.String.check(Schema.isNonEmpty()),
  permissions: Schema.Array(PermissionSchema),
}) {}

/** A member of the caller's organization. */
export class OrganizationMember extends Schema.Class<OrganizationMember>("OrganizationMember")({
  memberId: Schema.String,
  email: Schema.String,
  role: Schema.String,
}) {}

/** One member-level adjustment, as stored. */
export class MemberOverride extends Schema.Class<MemberOverride>("MemberOverride")({
  memberId: Schema.String,
  permission: PermissionSchema,
  granted: Schema.Boolean,
}) {}

/**
 * Managing who can do what.
 *
 * Every procedure is guarded by the `ac` resource — better-auth's own name for
 * "administering access control" — so the right to change permissions is itself
 * a permission, and an admin cannot quietly grant themselves more.
 */
export const AccessRpcs = RpcGroup.make(
  Rpc.make("ListRoles", {
    success: Schema.Array(CustomRole),
    error: Forbidden,
  }),
  /** Creates or replaces a custom role. */
  Rpc.make("SetRole", {
    payload: { role: CustomRole },
    success: Schema.Void,
    error: Forbidden,
  }),
  Rpc.make("DeleteRole", {
    payload: { role: Schema.String.check(Schema.isNonEmpty()) },
    success: Schema.Void,
    error: Forbidden,
  }),
  Rpc.make("ListMembers", {
    success: Schema.Array(OrganizationMember),
    error: Forbidden,
  }),
  Rpc.make("ListMemberOverrides", {
    payload: { memberId: Schema.String },
    success: Schema.Array(MemberOverride),
    error: Forbidden,
  }),
  /** Grants or revokes one permission for one member. */
  Rpc.make("SetMemberOverride", {
    payload: { override: MemberOverride },
    success: Schema.Void,
    error: Forbidden,
  }),
  Rpc.make("ClearMemberOverride", {
    payload: { memberId: Schema.String, permission: PermissionSchema },
    success: Schema.Void,
    error: Forbidden,
  }),
).middleware(AuthMiddleware);
