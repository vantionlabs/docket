import { sameIds, stable } from "@/atom/stable.js";
import { AsyncResult, Atom, AtomRegistry } from "effect/unstable/reactivity";
import { describe, expect, it } from "vitest";

/**
 * The identity repair `stable` exists to perform.
 *
 * Every subscriber compares by identity — `useAtomValue` maps before subscribing
 * and React bails out on `Object.is` — so a refetch that decodes the same bytes
 * into fresh objects re-renders everything downstream for nothing. `get.self()`
 * is what lets a recomputation decline to replace the value it already produced.
 */
describe("stable", () => {
  const rows = (ids: ReadonlyArray<string>) => ids.map((id) => ({ id }));

  it("hands back the identical value when the answer has not changed", () => {
    let source = AsyncResult.success(rows(["a", "b"]));
    const sourceAtom = Atom.make(() => source);
    const stableAtom = stable<ReadonlyArray<{ readonly id: string; }>, never>(
      (get) => get(sourceAtom),
      sameIds,
    );

    const registry = AtomRegistry.make();
    const unmount = registry.mount(stableAtom);

    const first = registry.get(stableAtom);

    // A refetch: same rows, freshly decoded, so a different array instance.
    source = AsyncResult.success(rows(["a", "b"]));
    registry.refresh(sourceAtom);

    expect(registry.get(stableAtom)).toBe(first);
    unmount();
  });

  it("replaces the value when the answer has changed", () => {
    let source = AsyncResult.success(rows(["a", "b"]));
    const sourceAtom = Atom.make(() => source);
    const stableAtom = stable<ReadonlyArray<{ readonly id: string; }>, never>(
      (get) => get(sourceAtom),
      sameIds,
    );

    const registry = AtomRegistry.make();
    const unmount = registry.mount(stableAtom);

    const first = registry.get(stableAtom);

    source = AsyncResult.success(rows(["a", "b", "c"]));
    registry.refresh(sourceAtom);

    expect(registry.get(stableAtom)).not.toBe(first);
    unmount();
  });
});

/** Order is part of the comparison, not just membership. */
describe("sameIds", () => {
  it("is true for the same ids in the same order", () => {
    expect(sameIds([{ id: "a" }, { id: "b" }], [{ id: "a" }, { id: "b" }])).toBe(true);
  });

  it("is false when the order differs", () => {
    expect(sameIds([{ id: "a" }, { id: "b" }], [{ id: "b" }, { id: "a" }])).toBe(false);
  });

  it("is false when the length differs", () => {
    expect(sameIds([{ id: "a" }], [{ id: "a" }, { id: "b" }])).toBe(false);
  });
});
