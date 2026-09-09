import { AppRpc } from "@/atom/app-rpc.js";
import { Keys } from "@/atom/reactivity-keys.js";
import { DecisionId } from "@forge/domain/decision/DecisionRpc";
import { Effect } from "effect";
import { Atom } from "effect/unstable/reactivity";

/**
 * The queue and the two ways out of it.
 *
 * Reads are declared by naming the RPC; writes stay hand-written so that "what
 * does this invalidate" lives next to the write rather than at every call site.
 */
const reads = [Keys.organization, Keys.decisions];

/**
 * Only what is waiting on a person. A decision that has been reviewed has left
 * the queue, which is the whole point of the screen -- it empties.
 */
export const queueAtom = AppRpc.query("ListQueue", { status: "pending_review" }, {
  reactivityKeys: reads,
});

/** One decision in full, keyed so each gets its own atom. */
export const decisionAtom = Atom.family((id: string) =>
  Atom.withReactivity(reads)(
    AppRpc.runtime.atom(
      Effect.gen(function*() {
        const client = yield* AppRpc;

        return yield* client("GetDecision", { id: DecisionId.make(id) });
      }),
    ),
  )
);

export const approveDecisionAtom = AppRpc.runtime.fn<{
  readonly id: DecisionId;
  readonly overrideOutcome: string | null;
  readonly note: string | null;
}>()(
  (input) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("ApproveDecision", input);
    }),
  { reactivityKeys: [Keys.decisions] },
);

export const rejectDecisionAtom = AppRpc.runtime.fn<{
  readonly id: DecisionId;
  readonly note: string | null;
}>()(
  (input) =>
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("RejectDecision", input);
    }),
  { reactivityKeys: [Keys.decisions] },
);
