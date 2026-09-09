import { Keys } from "@/atom/reactivity-keys.js";
import { Effect, Layer } from "effect";
import { Atom, AtomRegistry } from "effect/unstable/reactivity";
import { describe, expect, it } from "vitest";

/** Lets the atom runtime build its layer and settle the effect. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("reactivity keys", () => {
  /**
   * The whole point of the keys is that they cross module boundaries. Each atom
   * module builds its own `Atom.runtime`, so a switch published by
   * `organization-atoms` only reaches the queries in `contact-atoms` and
   * `access-atoms` if those separate runtimes share one `Reactivity` service.
   * They do — the default factory memoises it per registry — and this test
   * fails if that ever stops being true.
   */
  it("refreshes a query in one runtime when another runtime's mutation invalidates the key", async () => {
    const reads = Atom.runtime(Layer.empty);
    const writes = Atom.runtime(Layer.empty);

    let queried = 0;
    const listAtom = Atom.withReactivity([Keys.organization])(
      reads.atom(Effect.sync(() => ++queried)),
    );
    const switchAtom = writes.fn<void>()(() => Effect.void, {
      reactivityKeys: [Keys.organization],
    });

    const registry = AtomRegistry.make();
    const unmount = registry.mount(listAtom);
    await settle();
    expect(queried).toBe(1);

    registry.set(switchAtom, undefined);
    await settle();

    expect(queried).toBe(2);
    unmount();
  });

  it("leaves queries alone when an unrelated key is invalidated", async () => {
    const reads = Atom.runtime(Layer.empty);
    const writes = Atom.runtime(Layer.empty);

    let queried = 0;
    const listAtom = Atom.withReactivity([Keys.organization])(
      reads.atom(Effect.sync(() => ++queried)),
    );
    const renameContactAtom = writes.fn<void>()(() => Effect.void, {
      reactivityKeys: [Keys.contacts],
    });

    const registry = AtomRegistry.make();
    const unmount = registry.mount(listAtom);
    await settle();

    registry.set(renameContactAtom, undefined);
    await settle();

    expect(queried).toBe(1);
    unmount();
  });

  /**
   * A failed switch must not invalidate: the UI would otherwise re-read every
   * org-scoped query as though the organization had changed, and land back on
   * the same data having flashed a loading state for nothing.
   */
  it("does not invalidate when the mutation fails", async () => {
    const reads = Atom.runtime(Layer.empty);
    const writes = Atom.runtime(Layer.empty);

    let queried = 0;
    const listAtom = Atom.withReactivity([Keys.organization])(
      reads.atom(Effect.sync(() => ++queried)),
    );
    const failingSwitchAtom = writes.fn<void>()(() => Effect.fail("nope" as const), {
      reactivityKeys: [Keys.organization],
    });

    const registry = AtomRegistry.make();
    const unmount = registry.mount(listAtom);
    await settle();

    registry.set(failingSwitchAtom, undefined);
    await settle();

    expect(queried).toBe(1);
    unmount();
  });
});
