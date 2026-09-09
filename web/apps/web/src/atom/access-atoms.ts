import { AppRpc } from "@/atom/app-rpc.js";
import { Keys } from "@/atom/reactivity-keys.js";
import type { CustomRole, MemberOverride } from "@forge/domain/iam/AccessRpc";
import type { Permission } from "@forge/domain/iam/Permission";
import { Effect } from "effect";
import { Atom } from "effect/unstable/reactivity";

export const rolesAtom = Atom.withReactivity([Keys.organization, Keys.roles])(
  AppRpc.runtime.atom(
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("ListRoles", undefined);
    }),
  ),
);

export const membersAtom = Atom.withReactivity([Keys.organization, Keys.members])(
  AppRpc.runtime.atom(
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("ListMembers", undefined);
    }),
  ),
);

/** Overrides for one member, keyed so each member gets its own atom. */
export const memberOverridesAtom = Atom.family((memberId: string) =>
  Atom.withReactivity([Keys.organization, Keys.overrides])(
    AppRpc.runtime.atom(
      Effect.gen(function*() {
        const client = yield* AppRpc;

        return yield* client("ListMemberOverrides", { memberId });
      }),
    ),
  )
);

/**
 * Editing a role also invalidates `members`: the member table renders the role
 * each member holds, so it is stale the moment a role's permissions change.
 */
export const setRoleAtom = AppRpc.runtime.fn<CustomRole>()(
  (role) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("SetRole", { role });
    }),
  { reactivityKeys: [Keys.roles, Keys.members] },
);

export const deleteRoleAtom = AppRpc.runtime.fn<string>()(
  (role) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("DeleteRole", { role });
    }),
  { reactivityKeys: [Keys.roles, Keys.members] },
);

export const setOverrideAtom = AppRpc.runtime.fn<MemberOverride>()(
  (override) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("SetMemberOverride", { override });
    }),
  { reactivityKeys: [Keys.overrides] },
);

export const clearOverrideAtom = AppRpc.runtime.fn<
  { readonly memberId: string; readonly permission: Permission; }
>()(
  (input) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("ClearMemberOverride", input);
    }),
  { reactivityKeys: [Keys.overrides] },
);
