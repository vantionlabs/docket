import { describe, expect, it } from "@effect/vitest";
import type { Role } from "@forge/domain/iam/Permission";
import { grantsFor, permissionsFor, statements } from "@forge/domain/iam/Permission";
import { defaultRoles, defaultStatements } from "better-auth/plugins/organization/access";

const ourStatements: Record<string, ReadonlyArray<string>> = statements;

const flattenRole = (grants: Record<string, ReadonlyArray<string>>) =>
  Object.entries(grants).flatMap(([resource, actions]) =>
    actions.map((action) => `${resource}:${action}`)
  );

/**
 * These assertions are the reconciliation.
 *
 * better-auth enforces its own endpoints (invites, member removal, org
 * deletion) against the roles we hand it, while our RPC policies enforce ours
 * against `permissionsFor`. Both derive from `grantsFor`, and these tests fail
 * if that stops being true — either by our declaration drifting from what
 * better-auth's endpoints check, or by a role losing a grant they depend on.
 */
describe("access control reconciliation", () => {
  it("declares every resource and action better-auth checks", () => {
    for (const [resource, actions] of Object.entries(defaultStatements)) {
      const ours = ourStatements[resource];

      expect(ours, `resource "${resource}" is missing from our statements`).toBeDefined();
      for (const action of actions) {
        expect(ours, `"${resource}:${action}" is missing from our statements`).toContain(action);
      }
    }
  });

  it("keeps owner and admin able to do what better-auth's defaults allow", () => {
    // Withholding `organization:delete` from admins is ours to decide, and the
    // one documented divergence from better-auth's defaults.
    const intentional = new Set(["organization:delete"]);

    for (const role of ["owner", "admin"] as const) {
      const theirs = flattenRole(defaultRoles[role].statements);
      const ours = permissionsFor(role);

      for (const granted of theirs) {
        if (role === "admin" && intentional.has(granted)) continue;

        expect(ours.has(granted as never), `${role} lost "${granted}"`).toBe(true);
      }
    }
  });

  it("does not hand a member anything better-auth's default member lacks", () => {
    const theirs = new Set(flattenRole(defaultRoles.member.statements));

    for (const granted of permissionsFor("member")) {
      // `contact` is ours alone; better-auth has never heard of it.
      if (granted.startsWith("contact:")) continue;

      expect(theirs.has(granted), `member gained "${granted}" beyond better-auth's default`).toBe(
        true,
      );
    }
  });

  it("covers every role the domain can produce", () => {
    const roles: ReadonlyArray<Role> = ["owner", "admin", "member"];

    for (const role of roles) expect(grantsFor[role]).toBeDefined();
  });
});
