import { Schema } from "effect";

/**
 * What happened, who did it, and whether it was allowed.
 *
 * The design goal is coverage by default. Anything that is not obviously a read
 * is audited, so adding a new mutation logs it without anybody remembering to —
 * the opposite of a per-handler call that gets forgotten on the one endpoint
 * somebody later wishes had been recorded.
 */

export const AuditOutcome = Schema.Literals(["ok", "denied", "error"]).annotate({
  identifier: "AuditOutcome",
});
export type AuditOutcome = typeof AuditOutcome.Type;

/**
 * Keys that may be copied out of an RPC payload and into the log.
 *
 * An allowlist, not a denylist, and it is the whole security story of this
 * feature. Logging payloads wholesale would have written an access token and a
 * webhook signing secret into a table that half the organization can read; a
 * denylist would have done the same the first time somebody added a field
 * nobody thought to exclude.
 */
export const auditableKeys = [
  "id",
  "memberId",
  "contactId",
  "orgId",
  "role",
  "name",
  "email",
  "status",
  "kind",
  "permission",
  "active",
  "reason",
] as const;

/** Names that only read. Everything else is treated as a change and recorded. */
const readOnlyPrefixes = ["List", "Get", "Check"] as const;

export const isReadOnlyAction = (action: string): boolean =>
  action === "Me" || readOnlyPrefixes.some((prefix) => action.startsWith(prefix));

/**
 * Copies the allowlisted keys out of a payload.
 *
 * Values are stringified and truncated: an audit row is a record that something
 * happened, not a copy of the request. A long template body in here would make
 * the log expensive to read and tempting to use as a data store.
 */
const primitive = (value: unknown): string | null =>
  typeof value === "string"
    ? value
    : typeof value === "number" || typeof value === "boolean" || typeof value === "bigint"
    ? String(value)
    : null;

export const auditableFields = (payload: unknown): Record<string, string> => {
  if (typeof payload !== "object" || payload === null) return {};

  const fields: Record<string, string> = {};

  for (const key of auditableKeys) {
    const value = (payload as Record<string, unknown>)[key];
    if (value === undefined || value === null) continue;

    // Only scalars and arrays of them. An object would render as
    // "[object Object]", which is noise in a log somebody has to read.
    const rendered = Array.isArray(value)
      ? value.map((entry) => primitive(entry)).filter((entry) => entry !== null).join(", ")
      : primitive(value);

    if (rendered === null || rendered === "") continue;

    fields[key] = rendered.slice(0, 200);
  }

  return fields;
};

export class AuditEntry extends Schema.Class<AuditEntry>("AuditEntry")({
  id: Schema.String,
  /** The RPC name — `CreateContact`, `CreateApiKey`, `DeleteOrganization`. */
  action: Schema.String,
  outcome: AuditOutcome,
  actorEmail: Schema.String,
  actorRole: Schema.String,
  /** Allowlisted payload fields, flattened for display. */
  detail: Schema.String,
  at: Schema.DateTimeUtcFromString,
}) {}
