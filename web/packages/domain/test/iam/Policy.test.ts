import { describe, expect, it } from "@effect/vitest";
import { CurrentUser, Identity, OrgId, UserId } from "@forge/domain/iam/Identity";
import type { Role } from "@forge/domain/iam/Permission";
import { permissionsFor, resolvePermissions } from "@forge/domain/iam/Permission";
import { all, any, Forbidden, permission } from "@forge/domain/iam/Policy";
import { Effect, Layer } from "effect";

const as = (role: Role) =>
  Layer.succeed(CurrentUser)(
    new Identity({
      userId: UserId.make("user_1"),
      orgId: OrgId.make("org_1"),
      email: "someone@example.com",
      emailVerified: true,
      role,
      permissions: Array.from(permissionsFor(role)),
    }),
  );

describe("permissionsFor", () => {
  it("gives an owner strictly more than an admin", () => {
    const owner = permissionsFor("owner");
    const admin = permissionsFor("admin");

    expect(admin.has("organization:delete")).toBe(false);
    expect(owner.has("organization:delete")).toBe(true);
    // Everything an admin can do, an owner can do.
    for (const granted of admin) expect(owner.has(granted)).toBe(true);
  });

  it("does not let a member manage other members", () => {
    const member = permissionsFor("member");

    expect(member.has("contact:read")).toBe(true);
    expect(member.has("member:create")).toBe(false);
    expect(member.has("member:delete")).toBe(false);
  });
});

describe("policies", () => {
  it.effect("allow the role that holds the permission", () =>
    permission("organization:delete").pipe(Effect.provide(as("owner"))));

  it.effect("deny the role that does not, naming what was required", () =>
    Effect.gen(function*() {
      const error = yield* Effect.flip(permission("organization:delete"));

      expect(error).toBeInstanceOf(Forbidden);
      expect(error.required).toBe("organization:delete");
    }).pipe(Effect.provide(as("admin"))));

  it.effect("`all` fails when any policy fails", () =>
    Effect.gen(function*() {
      const error = yield* Effect.flip(
        all(permission("contact:read"), permission("organization:delete")),
      );

      expect(error.required).toBe("organization:delete");
    }).pipe(Effect.provide(as("member"))));

  it.effect("`any` succeeds when one policy passes", () =>
    any(permission("organization:delete"), permission("contact:read")).pipe(
      Effect.provide(as("member")),
    ));
});

describe("resolvePermissions", () => {
  it("starts a custom role from nothing, then adds its grants", () => {
    const resolved = resolvePermissions({
      role: "editor",
      customRoleGrants: ["contact:read", "contact:update"],
      overrides: [],
    });

    expect(Array.from(resolved).sort()).toEqual(["contact:read", "contact:update"]);
  });

  it("lets an override revoke something the role grants", () => {
    const resolved = resolvePermissions({
      role: "admin",
      customRoleGrants: [],
      overrides: [{ permission: "member:delete", granted: false }],
    });

    expect(permissionsFor("admin").has("member:delete")).toBe(true);
    expect(resolved.has("member:delete")).toBe(false);
    // Everything else the role gave is untouched.
    expect(resolved.has("member:create")).toBe(true);
  });

  it("lets an override grant something the role does not", () => {
    const resolved = resolvePermissions({
      role: "member",
      customRoleGrants: [],
      overrides: [{ permission: "invitation:create", granted: true }],
    });

    expect(resolved.has("invitation:create")).toBe(true);
  });

  it("applies revokes after custom-role grants, so a revoke wins", () => {
    const resolved = resolvePermissions({
      role: "member",
      customRoleGrants: ["contact:delete"],
      overrides: [{ permission: "contact:delete", granted: false }],
    });

    expect(resolved.has("contact:delete")).toBe(false);
  });
});
