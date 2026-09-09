import { describe, expect, it } from "@effect/vitest";
import { Deferred, Effect } from "effect";
import { AsyncResult, Atom, AtomRegistry } from "effect/unstable/reactivity";

describe("Atom runtime wiring", () => {
  it("holds Initial until the effect completes, then reports Success", async () => {
    const registry = AtomRegistry.make();
    const gate = Deferred.makeUnsafe<string>();
    const atom = Atom.make(Deferred.await(gate));

    const settled = new Promise<AsyncResult.AsyncResult<string>>((resolve) => {
      registry.subscribe(atom, (result) => {
        if (AsyncResult.isNotInitial(result)) resolve(result);
      });
    });
    registry.mount(atom);

    expect(AsyncResult.isInitial(registry.get(atom))).toBe(true);

    Deferred.doneUnsafe(gate, Effect.succeed("ok"));
    const result = await settled;

    expect(AsyncResult.isSuccess(result)).toBe(true);
    registry.dispose();
  });
});
