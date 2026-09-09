import { DecisionRpcs } from "@forge/domain/decision/DecisionRpc";
import { Effect } from "effect";
import { DecisionStore } from "./DecisionStore.js";

/**
 * The RPC transport over the shared store.
 *
 * Nothing but mapping: every policy check, every org scope and every statement
 * lives in `DecisionStore`, so the public API can serve the same behaviour
 * without a second implementation of "approve a decision".
 */
export const DecisionRpcLive = DecisionRpcs.toLayer(
  Effect.gen(function*() {
    const decisions = yield* DecisionStore;

    return DecisionRpcs.of({
      ListQueue: (payload) => decisions.list(payload.status),

      GetDecision: (payload) => decisions.get(payload.id),

      ApproveDecision: (payload) => decisions.approve(payload),

      RejectDecision: (payload) => decisions.reject(payload),
    });
  }),
);
