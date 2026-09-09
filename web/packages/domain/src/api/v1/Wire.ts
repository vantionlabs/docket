import { Schema } from "effect";

/**
 * The v1 public contract. Frozen.
 *
 * These are deliberately *not* the domain types, and that separation is the
 * whole of what makes versioning real rather than aspirational. If the public
 * API returned `Contact` directly, renaming a field in the domain — or adding a
 * required one — would silently break every customer's integration, and nothing
 * in the build would say so. Here a domain change breaks the *mapping*, which is
 * a compile error in one file, and the person making it has to decide
 * consciously whether v1 keeps its old shape or a v2 is needed.
 *
 * The rules for this file:
 *
 * - Nothing is renamed or removed. Ever. That is what v2 is for.
 * - New fields may be added, but only optional ones — a client written against
 *   an earlier v1 must keep working.
 * - No domain type is re-exported into it, however convenient.
 *
 * Field names are snake_case because that is what a public JSON API is expected
 * to look like, and the domain's camelCase is not part of the promise.
 */

export class ContactV1 extends Schema.Class<ContactV1>("ContactV1")({
  id: Schema.String,
  email: Schema.String,
  full_name: Schema.String,
}) {}

export class NewContactV1 extends Schema.Class<NewContactV1>("NewContactV1")({
  email: Schema.String.check(Schema.isNonEmpty()),
  full_name: Schema.String.check(Schema.isNonEmpty()),
}) {}

/**
 * Errors are part of the contract too.
 *
 * A caller writing a retry needs to distinguish "your key is wrong" from "you
 * asked for something that does not exist", and those meanings have to survive
 * a version.
 *
 * One class per status, not one class at three statuses. That is not stylistic:
 * the response status is chosen by matching the failure against the declared
 * error *schemas*, so three declarations sharing a single schema all resolve to
 * whichever was declared first — a 404 that goes out as a 401.
 */
export class Unauthorized extends Schema.Class<Unauthorized>("Unauthorized")({
  error: Schema.tag("unauthorized"),
  message: Schema.String,
}) {}

export class Forbidden extends Schema.Class<Forbidden>("Forbidden")({
  error: Schema.tag("forbidden"),
  message: Schema.String,
}) {}

export class NotFound extends Schema.Class<NotFound>("NotFound")({
  error: Schema.tag("not_found"),
  message: Schema.String,
}) {}
