import {
  ContactV1,
  Forbidden,
  NewContactV1,
  NotFound,
  Unauthorized,
} from "@forge/domain/api/v1/Wire";
import { Schema } from "effect";
import { describe, expect, it } from "vitest";

/**
 * The v1 contract, pinned.
 *
 * These assertions exist to fail. A domain rename that reaches the public API,
 * a field quietly dropped, a type widened — each one breaks somebody's
 * integration silently, and nothing else in the build would notice. Spelling the
 * shape out here turns that into a failing test whose only correct resolutions
 * are "map it back" or "this is v2".
 *
 * Adding an *optional* field is allowed and should not fail: it cannot break a
 * client written against an earlier v1.
 */

const fieldsOf = (schema: { readonly fields: Record<string, unknown>; }) =>
  Object.keys(schema.fields).sort();

describe("v1 wire contract", () => {
  it("pins the contact shape", () => {
    expect(fieldsOf(ContactV1)).toEqual(["email", "full_name", "id"]);
  });

  it("pins what creating a contact accepts", () => {
    expect(fieldsOf(NewContactV1)).toEqual(["email", "full_name"]);
  });

  /** snake_case is the promise. The domain's camelCase is not part of it. */
  it("exposes no camelCase field", () => {
    for (const schema of [ContactV1, NewContactV1]) {
      for (const field of fieldsOf(schema)) {
        expect(field, field).toBe(field.toLowerCase());
      }
    }
  });

  /**
   * One class per status, not one class at three statuses. The response status
   * is chosen by matching the failure against the declared error *schemas*, so
   * three declarations sharing a schema all resolve to whichever was declared
   * first — a 404 that goes out as a 401.
   */
  it("gives each error its own discriminant", () => {
    const tags = [Unauthorized, Forbidden, NotFound].map((schema) =>
      Schema.decodeUnknownSync(schema)({ error: schemaTag(schema), message: "x" }).error
    );

    expect(new Set(tags).size).toBe(3);
  });
});

/** The literal each error class tags itself with, read back off the schema. */
function schemaTag(schema: typeof Unauthorized | typeof Forbidden | typeof NotFound): string {
  return schema === Unauthorized
    ? "unauthorized"
    : schema === Forbidden
    ? "forbidden"
    : "not_found";
}
