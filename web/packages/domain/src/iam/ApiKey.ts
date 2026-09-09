import { Schema } from "effect";

/**
 * A credential for calling the app without a browser session.
 *
 * Three decisions, all of them about what happens when a key leaks.
 *
 * It is **hashed** at rest. A key is a bearer credential, so a dump of this
 * table must not be a set of working keys — the same reason passwords are not
 * stored. SHA-256 without a salt is deliberate and sufficient here: the input is
 * 32 bytes of CSPRNG output, so there is no dictionary to attack and no
 * plausible rainbow table.
 *
 * It carries a **prefix in clear**, because a key that cannot be identified
 * cannot be revoked. When one turns up in a public repository the owner needs to
 * find it in a list, and comparing hashes by hand is not that.
 *
 * It is **scoped to a role**, not to a user. A key that inherited whoever
 * created it would silently gain capabilities when that person was promoted, and
 * keep them after they left.
 */

/** `forge_live_` then 32 random bytes, hex. The prefix makes it greppable. */
export const KEY_PREFIX = "forge_live_";

/** How much of the key is stored in clear for identification. */
export const HINT_LENGTH = 8;

export const hint = (key: string): string =>
  key.slice(KEY_PREFIX.length, KEY_PREFIX.length + HINT_LENGTH);

export class ApiKey extends Schema.Class<ApiKey>("ApiKey")({
  id: Schema.String,
  name: Schema.String,
  /** Characters after the prefix, enough to recognise which key this is. */
  hint: Schema.String,
  role: Schema.String,
  createdAt: Schema.DateTimeUtcFromString,
  lastUsedAt: Schema.NullOr(Schema.DateTimeUtcFromString),
}) {}

/** Returned once, at creation. Nothing else ever returns the key itself. */
export class CreatedApiKey extends Schema.Class<CreatedApiKey>("CreatedApiKey")({
  key: ApiKey,
  secret: Schema.String,
}) {}

/**
 * Is this plausibly one of our keys?
 *
 * A cheap shape check before hashing, so a malformed `Authorization` header is
 * rejected without a database round trip.
 */
export const looksLikeApiKey = (value: string): boolean =>
  value.startsWith(KEY_PREFIX) && value.length === KEY_PREFIX.length + 64;
