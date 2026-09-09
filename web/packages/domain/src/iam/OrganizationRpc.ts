import { Schema } from "effect";
import { Rpc, RpcGroup } from "effect/unstable/rpc";
import { ApiKey, CreatedApiKey } from "./ApiKey.js";
import { AuditEntry } from "./Audit.js";
import { AuthMiddleware } from "./AuthMiddleware.js";
import { OrgId } from "./Identity.js";
import { Role } from "./Permission.js";
import { Forbidden } from "./Policy.js";

/** An organization the caller belongs to, with their role in it. */
export class Membership extends Schema.Class<Membership>("Membership")({
  orgId: OrgId,
  name: Schema.String,
  slug: Schema.String,
  role: Schema.String,
  isActive: Schema.Boolean,
}) {}

/**
 * Deleting the only organization somebody belongs to.
 *
 * Refused rather than handled: an account with no organization has nothing to
 * show and no way back in, so the app would have to invent one on next sign-in.
 * Creating a second one first is the answer, and it is one the user can act on.
 */
export class LastOrganization extends Schema.TaggedError<LastOrganization>()("LastOrganization", {
  orgId: OrgId,
}) {}

/** The typed name did not match the organization being deleted. */
export class NameMismatch extends Schema.TaggedError<NameMismatch>()("NameMismatch", {
  orgId: OrgId,
}) {}

/** Switching to an organization the caller does not belong to. */
export class NotAMember extends Schema.TaggedError<NotAMember>()("NotAMember", {
  orgId: OrgId,
}) {}

/**
 * Organization management, kept apart from the identity group because these
 * handlers reach the database and those do not.
 */
export const OrganizationRpcs = RpcGroup.make(
  /** Every organization the caller belongs to — the switcher\'s source of truth. */
  Rpc.make("ListMyOrganizations", { success: Schema.Array(Membership) }),
  /** Creates an organization and makes the caller its owner. */
  Rpc.make("CreateOrganization", {
    payload: { name: Schema.String.check(Schema.isNonEmpty()) },
    success: Membership,
  }),
  /** Points the current session at another of the caller\'s organizations. */
  Rpc.make("SwitchOrganization", {
    payload: { orgId: OrgId },
    success: Schema.Void,
    error: NotAMember,
  }),
  /**
   * Requires `organization:update`, which only an owner holds — the
   * demonstration that policies gate real procedures.
   */
  Rpc.make("RenameOrganization", {
    payload: { name: Schema.String.check(Schema.isNonEmpty()) },
    success: Schema.Void,
    error: Forbidden,
  }),
  /**
   * Deletes the active organization and everything in it.
   *
   * The name is required in the payload and checked against the record. Not
   * validation — a confirmation: the destructive request cannot be replayed
   * against a different organization after a switch, because the name would no
   * longer match.
   */
  Rpc.make("DeleteOrganization", {
    payload: { confirmName: Schema.String.check(Schema.isNonEmpty()) },
    success: Schema.Void,
    error: Schema.Union([Forbidden, LastOrganization, NameMismatch]),
  }),
  Rpc.make("ListApiKeys", { success: Schema.Array(ApiKey), error: Forbidden }),
  /**
   * The only time a key is returned. Creating one is an owner-level act: a key
   * is a credential that bypasses the browser session entirely.
   */
  Rpc.make("CreateApiKey", {
    payload: {
      name: Schema.String.check(Schema.isNonEmpty()),
      role: Role,
    },
    success: CreatedApiKey,
    error: Forbidden,
  }),
  Rpc.make("RevokeApiKey", {
    payload: { id: Schema.String },
    success: Schema.Void,
    error: Forbidden,
  }),
  /** The org-wide audit trail, newest first. */
  Rpc.make("ListAuditLog", {
    payload: { limit: Schema.Int.check(Schema.isBetween({ minimum: 1, maximum: 200 })) },
    success: Schema.Array(AuditEntry),
    error: Forbidden,
  }),
).middleware(AuthMiddleware);
