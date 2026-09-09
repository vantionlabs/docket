import { AppRpc } from "@/atom/app-rpc.js";
import { Keys } from "@/atom/reactivity-keys.js";
import type { ContactId } from "@forge/domain/contact/ContactRpc";
import { Effect } from "effect";

/**
 * Reads are declared by naming the RPC; writes stay hand-written.
 *
 * `AppRpc.query` builds the atom, so there is no service to yield and no effect
 * to write for a plain fetch. `AppRpc.mutation` exists too, but its reactivity
 * keys are supplied per *call* rather than per definition — which would scatter
 * "what does this invalidate" across every call site and make it something to
 * forget. Keeping writes as `runtime.fn` keeps that answer in one place, next to
 * the write it belongs to.
 */
const reads = [Keys.organization, Keys.contacts];

export const contactsAtom = AppRpc.query("ListContacts", undefined, { reactivityKeys: reads });

export const overviewAtom = AppRpc.query("GetOverview", undefined, { reactivityKeys: reads });

export const createContactAtom = AppRpc.runtime.fn<
  { readonly email: string; readonly fullName: string; }
>()(
  (input) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("CreateContact", input);
    }),
  { reactivityKeys: [Keys.contacts] },
);

export const deleteContactAtom = AppRpc.runtime.fn<ContactId>()(
  (id) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("DeleteContact", { id });
    }),
  { reactivityKeys: [Keys.contacts] },
);
