import { Context, Schema } from "effect";
import { PermissionSchema } from "./Permission.js";

/**
 * Branded ids. Construct with `UserId.make(value)`, which validates — never
 * cast with `as`.
 */
export const UserId = Schema.String.pipe(Schema.brand("UserId")).annotate({
  identifier: "UserId",
});
export type UserId = typeof UserId.Type;

export const OrgId = Schema.String.pipe(Schema.brand("OrgId")).annotate({
  identifier: "OrgId",
});
export type OrgId = typeof OrgId.Type;

/**
 * The authenticated caller, as the rest of the system sees them.
 *
 * `orgId` is always present: a personal organization is created alongside every
 * user, so there is no orgless state to represent.
 */
export class Identity extends Schema.Class<Identity>("Identity")({
  userId: UserId,
  orgId: OrgId,
  email: Schema.String,
  emailVerified: Schema.Boolean,
  /**
   * Membership role in `orgId`. A plain string, not a fixed union — dynamic
   * access control lets an organization define roles of its own.
   */
  role: Schema.String,
  /**
   * Effective permissions, already resolved from the role, any custom role and
   * the member's own overrides. This is what policies read; `role` is for
   * display.
   */
  permissions: Schema.Array(PermissionSchema),
}) {}

/**
 * Provided by the RPC auth middleware. Handlers read the caller — and their org
 * scope — from here rather than taking it as an argument, which is what keeps a
 * request from ever naming another tenant's org.
 */
export class CurrentUser extends Context.Service<CurrentUser, Identity>()("CurrentUser") {}

/**
 * The authentication failures a caller can act on. Everything else — a broken
 * adapter, a misconfigured secret — is a defect.
 */
export class Unauthenticated extends Schema.TaggedError<Unauthenticated>()("Unauthenticated", {
  reason: Schema.Literals(["NoSession", "SessionExpired", "NoActiveOrganization"]),
}) {}
