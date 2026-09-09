import { AppRpc } from "@/atom/app-rpc.js";
import { Keys } from "@/atom/reactivity-keys.js";
import type { OrgId } from "@forge/domain/iam/Identity";
import type { Role } from "@forge/domain/iam/Permission";
import { Effect } from "effect";
import { Atom } from "effect/unstable/reactivity";

export const organizationsAtom = Atom.withReactivity([Keys.organization])(
  AppRpc.runtime.atom(
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("ListMyOrganizations", undefined);
    }),
  ),
);

/**
 * Both writes invalidate `organization`, so the session, this list and every
 * org-scoped query re-read themselves once the switch actually lands. Keys are
 * only invalidated on success — a rejected switch leaves the UI on the
 * organization it is still in.
 */
export const switchOrganizationAtom = AppRpc.runtime.fn<OrgId>()(
  (orgId) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("SwitchOrganization", { orgId });
    }),
  { reactivityKeys: [Keys.organization] },
);

export const renameOrganizationAtom = AppRpc.runtime.fn<string>()(
  (name) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("RenameOrganization", { name });
    }),
  { reactivityKeys: [Keys.organization] },
);

/** Deleting the active organization moves the session, so everything re-reads. */
export const deleteOrganizationAtom = AppRpc.runtime.fn<string>()(
  (confirmName) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("DeleteOrganization", { confirmName });
    }),
  { reactivityKeys: [Keys.organization] },
);

export const apiKeysAtom = Atom.withReactivity([Keys.organization, Keys.apiKeys])(
  AppRpc.runtime.atom(
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("ListApiKeys", undefined);
    }),
  ),
);

export const createApiKeyAtom = AppRpc.runtime.fn<
  { readonly name: string; readonly role: Role; }
>()(
  (input) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("CreateApiKey", input);
    }),
  { reactivityKeys: [Keys.apiKeys] },
);

export const revokeApiKeyAtom = AppRpc.runtime.fn<string>()(
  (id) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("RevokeApiKey", { id });
    }),
  { reactivityKeys: [Keys.apiKeys] },
);

export const auditLogAtom = Atom.withReactivity([Keys.organization, Keys.audit])(
  AppRpc.runtime.atom(
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("ListAuditLog", { limit: 100 });
    }),
  ),
);

export const createOrganizationAtom = AppRpc.runtime.fn<string>()(
  (name) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("CreateOrganization", { name });
    }),
  { reactivityKeys: [Keys.organization] },
);
