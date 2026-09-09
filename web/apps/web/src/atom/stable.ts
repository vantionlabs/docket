import { Option } from "effect";
import { AsyncResult, Atom } from "effect/unstable/reactivity";

/**
 * A derived atom that keeps its identity when its answer has not changed.
 *
 * Every subscriber in the app compares by identity — `useAtomValue` maps before
 * subscribing, React bails out on `Object.is` — and a refetch defeats that even
 * when the bytes are the same, because decoding builds fresh objects. That is not
 * a rare case: any atom invalidated by a coarse key refetches lists whose rows
 * the invalidating write never touched.
 *
 * `get.self()` is what makes the repair possible — it hands back the value this
 * atom last produced, so the recomputation can decline to replace it. Comparing
 * with a supplied predicate rather than a deep equality keeps the cost bounded and
 * the intent explicit: the caller says which fields decide, and lists compare on
 * their ids rather than on everything hanging off them.
 *
 * Only the settled value is compared. An in-flight refetch does not push a
 * `waiting` value through, which is the point — subscribers here render data, not
 * spinners, and propagating the flag would restore the two re-renders per refetch
 * this exists to remove. An atom whose consumer *does* show a pending state should
 * not be wrapped in this.
 */
export const stable = <A, E>(
  compute: (get: Atom.AtomContext) => AsyncResult.AsyncResult<A, E>,
  same: (previous: A, next: A) => boolean,
): Atom.Atom<AsyncResult.AsyncResult<A, E>> =>
  Atom.readable((get) => {
    const next = compute(get);
    const previous = get.self<AsyncResult.AsyncResult<A, E>>();

    return Option.isSome(previous)
        && AsyncResult.isSuccess(previous.value)
        && AsyncResult.isSuccess(next)
        && same(previous.value.value, next.value)
      ? previous.value
      : next;
  });

/**
 * Sameness for an append-only list: same rows, same order.
 *
 * Sound only where a row's id implies its contents — an append-only log, or
 * messages written once and never edited. Do not reach for it on rows that keep
 * their id while their fields change underneath.
 */
export const sameIds = <A extends { readonly id: string; }>(
  previous: ReadonlyArray<A>,
  next: ReadonlyArray<A>,
): boolean =>
  previous.length === next.length
  && previous.every((row, index) => row.id === next[index]?.id);
