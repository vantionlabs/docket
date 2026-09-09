import { auditableFields, isReadOnlyAction } from "@forge/domain/iam/Audit";
import { describe, expect, it } from "vitest";

describe("isReadOnlyAction", () => {
  it("treats the reading verbs as reads", () => {
    for (const action of ["ListContacts", "GetOverview", "Me", "CheckSomething"]) {
      expect(isReadOnlyAction(action), action).toBe(true);
    }
  });

  /**
   * Coverage by default is the whole design. An unfamiliar action is audited,
   * so adding a mutation records it without anybody touching this file — the
   * failure mode of a denylist is a new endpoint silently going unlogged.
   */
  it("treats everything else as a change, including names it has never seen", () => {
    for (
      const action of [
        "CreateContact",
        "DeleteOrganization",
        "CreateApiKey",
        "SetMemberOverride",
        "SomethingNobodyHasWrittenYet",
      ]
    ) {
      expect(isReadOnlyAction(action), action).toBe(false);
    }
  });
});

/**
 * The allowlist is the security boundary of the audit log. These payloads carry
 * credentials, and the log is readable by anyone with `member:read`.
 */
describe("auditableFields", () => {
  it("never copies a credential, however it is named", () => {
    const fields = auditableFields({
      token: "pat-eu1-real-token",
      secret: "0123456789abcdef",
      password: "correct-horse",
      apiKey: "sk-live-1234",
      email: "someone@example.com",
    });

    // The address survives because it identifies the subject of the action; the
    // four beside it are credentials whatever they are called.
    expect(fields).toEqual({ email: "someone@example.com" });
    expect(JSON.stringify(fields)).not.toContain("pat-eu1");
    expect(JSON.stringify(fields)).not.toContain("0123456789");
  });

  it("copies the identifiers that make an entry useful", () => {
    expect(auditableFields({
      id: "ct_1",
      name: "Ada Lovelace",
      role: "member",
      status: "active",
    })).toEqual({
      id: "ct_1",
      name: "Ada Lovelace",
      role: "member",
      status: "active",
    });
  });

  it("flattens an array rather than stringifying the object", () => {
    expect(auditableFields({ permission: ["member:read", "member:create"] }).permission)
      .toBe("member:read, member:create");
  });

  /** Every value lands as a string, so a non-string one has to be coerced. */
  it("renders a non-string scalar", () => {
    expect(auditableFields({ active: true })).toEqual({ active: "true" });
  });

  /** A row records that something happened; it is not a copy of the request. */
  it("truncates a long value", () => {
    const fields = auditableFields({ name: "x".repeat(500) });

    expect(fields.name).toHaveLength(200);
  });

  it("skips absent values instead of writing nulls", () => {
    expect(auditableFields({ id: "a", name: null, status: undefined })).toEqual({ id: "a" });
  });

  it("copes with a payload that is not an object", () => {
    expect(auditableFields(undefined)).toEqual({});
    expect(auditableFields("a string")).toEqual({});
    expect(auditableFields(null)).toEqual({});
  });
});
