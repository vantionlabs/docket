import { Effect, Layer } from "effect";
import { Atom, AtomRegistry } from "effect/unstable/reactivity";
import { describe, expect, it } from "vitest";

/** Lets the registry build its layer and settle the effect. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/**
 * Why the app's registry is given an idle window.
 *
 * `AtomRegistry` only schedules a node for *timed* removal when an idle TTL
 * exists — with none it deletes the node the moment the last subscriber goes.
 * In a router that unmounts a page on every navigation, that meant re-fetching
 * data that had not changed each time somebody came back.
 *
 * This pins both halves of the bargain: the value survives a remount inside the
 * window, and the window is real rather than a cache that never lets go.
 */
describe("registry idle window", () => {
  it("reuses a value when a page remounts inside the window", async () => {
    let queried = 0;
    const runtime = Atom.runtime(Layer.empty);
    const dataAtom = runtime.atom(Effect.sync(() => ++queried));

    const registry = AtomRegistry.make({ defaultIdleTTL: 30_000 });

    const first = registry.mount(dataAtom);
    await settle();
    expect(queried).toBe(1);

    // Navigating away, then straight back.
    first();
    const second = registry.mount(dataAtom);
    await settle();

    expect(queried).toBe(1);
    second();
  });

  /**
   * The same sequence with no window, which is what the app did before and why
   * every navigation cost a round trip.
   */
  it("re-runs on remount when there is no window", async () => {
    let queried = 0;
    const runtime = Atom.runtime(Layer.empty);
    const dataAtom = runtime.atom(Effect.sync(() => ++queried));

    const registry = AtomRegistry.make();

    registry.mount(dataAtom)();
    await settle();
    const afterFirst = queried;

    registry.mount(dataAtom)();
    await settle();

    expect(queried).toBeGreaterThan(afterFirst);
  });
});
