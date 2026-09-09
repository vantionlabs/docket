import { Schema } from "effect";
import { Rpc, RpcGroup } from "effect/unstable/rpc";
import { AuthMiddleware } from "../iam/AuthMiddleware.js";
import { Forbidden } from "../iam/Policy.js";

export const ContactId = Schema.String.pipe(Schema.brand("ContactId")).annotate({
  identifier: "ContactId",
});
export type ContactId = typeof ContactId.Type;

/**
 * Someone an organization intends to reach out to.
 *
 * Deliberately thin: this is the worked example of a tenant-owned entity, and
 * the feature built on top decides what else a contact needs to carry.
 */
export class Contact extends Schema.Class<Contact>("Contact")({
  id: ContactId,
  email: Schema.String,
  fullName: Schema.String,
}) {}

/** Counts for the dashboard, in one round trip rather than three. */
export class Overview extends Schema.Class<Overview>("Overview")({
  contacts: Schema.Number,
  members: Schema.Number,
  customRoles: Schema.Number,
}) {}

export const ContactRpcs = RpcGroup.make(
  Rpc.make("ListContacts", { success: Schema.Array(Contact), error: Forbidden }),
  Rpc.make("CreateContact", {
    payload: {
      email: Schema.String.check(Schema.isNonEmpty()),
      fullName: Schema.String.check(Schema.isNonEmpty()),
    },
    success: Contact,
    error: Forbidden,
  }),
  Rpc.make("DeleteContact", {
    payload: { id: ContactId },
    success: Schema.Void,
    error: Forbidden,
  }),
  Rpc.make("GetOverview", { success: Overview, error: Forbidden }),
).middleware(AuthMiddleware);
