import { Schema } from "effect";
import { Rpc, RpcGroup } from "effect/unstable/rpc";
import { AuthMiddleware } from "../iam/AuthMiddleware.js";
import { Forbidden } from "../iam/Policy.js";

export const DecisionId = Schema.String.pipe(Schema.brand("DecisionId")).annotate({
  identifier: "DecisionId",
});
export type DecisionId = typeof DecisionId.Type;

/**
 * Where the case has got to, as distinct from what was decided.
 *
 * Closed, unlike `outcome`: these five are the pipeline's own vocabulary and
 * are the same whatever the document is. An outcome belongs to the vertical, so
 * it stays an open string here and in the database.
 */
export const DecisionStatus = Schema.Literals([
  "pending_review",
  "approved",
  "rejected",
  "executed",
  "failed",
]).annotate({ identifier: "DecisionStatus" });
export type DecisionStatus = typeof DecisionStatus.Type;

/** A policy clause that justified a decision, quoted verbatim. */
export class Citation extends Schema.Class<Citation>("Citation")({
  id: Schema.String,
  /** 1-based, matching the `[n]` markers in the rationale. */
  citationIndex: Schema.Finite,
  clauseRef: Schema.String,
  excerpt: Schema.String,
}) {}

/**
 * One row of the review queue.
 *
 * Deliberately not the whole decision: a reviewer clearing forty of these wants
 * the list to arrive in one round trip, and the rationale and citations are
 * only read on the one they open.
 */
export class DecisionSummary extends Schema.Class<DecisionSummary>("DecisionSummary")({
  id: DecisionId,
  outcome: Schema.String,
  /** What actually stands: the reviewer's call where they made one. */
  effectiveOutcome: Schema.String,
  status: DecisionStatus,
  /** A cost centre or a role, never a person. */
  assignedTo: Schema.NullOr(Schema.String),
  groundingPassed: Schema.Boolean,
  decidedAt: Schema.DateTimeUtcFromString,
}) {}

/** Everything the decision detail screen reads. */
export class Decision extends Schema.Class<Decision>("Decision")({
  id: DecisionId,
  outcome: Schema.String,
  effectiveOutcome: Schema.String,
  status: DecisionStatus,
  assignedTo: Schema.NullOr(Schema.String),
  decidedAt: Schema.DateTimeUtcFromString,

  /** What the model proposed before the rails moved it. */
  proposedOutcome: Schema.NullOr(Schema.String),
  rationale: Schema.String,
  unmetConditions: Schema.Array(Schema.String),
  railNotes: Schema.Array(Schema.String),

  ruleId: Schema.NullOr(Schema.String),
  groundingPassed: Schema.Boolean,
  groundingFailure: Schema.NullOr(Schema.String),

  /** Null means coverage was not checked, not that it was checked and clean. */
  coverageComplete: Schema.NullOr(Schema.Boolean),
  coverageRecall: Schema.NullOr(Schema.Finite),

  reviewedAt: Schema.NullOr(Schema.DateTimeUtcFromString),
  overrideOutcome: Schema.NullOr(Schema.String),
  overrideNote: Schema.NullOr(Schema.String),

  citations: Schema.Array(Citation),
}) {}

/** No decision with that id in the caller's organization. */
export class DecisionNotFound extends Schema.TaggedError<DecisionNotFound>()("DecisionNotFound", {
  id: DecisionId,
}) {}

export const DecisionRpcs = RpcGroup.make(
  /** The queue: pending decisions, oldest first. */
  Rpc.make("ListQueue", {
    payload: { status: Schema.NullOr(DecisionStatus) },
    success: Schema.Array(DecisionSummary),
    error: Forbidden,
  }),
  Rpc.make("GetDecision", {
    payload: { id: DecisionId },
    success: Decision,
    error: Schema.Union([Forbidden, DecisionNotFound]),
  }),
  /**
   * Approving is the same call whether or not the reviewer agrees.
   *
   * A non-null `overrideOutcome` is the disagreement: the pipeline's `outcome`
   * stays exactly as it was and the override sits beside it, because the gap
   * between the two is the override rate, and that is the number that tells a
   * client whether a rule is safe to widen.
   */
  Rpc.make("ApproveDecision", {
    payload: {
      id: DecisionId,
      overrideOutcome: Schema.NullOr(Schema.String),
      note: Schema.NullOr(Schema.String),
    },
    success: Schema.Void,
    error: Schema.Union([Forbidden, DecisionNotFound]),
  }),
  Rpc.make("RejectDecision", {
    payload: { id: DecisionId, note: Schema.NullOr(Schema.String) },
    success: Schema.Void,
    error: Schema.Union([Forbidden, DecisionNotFound]),
  }),
).middleware(AuthMiddleware);
