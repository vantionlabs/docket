"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { ApiError, api } from "@/lib/api";

export type Outcome =
  | "auto_approve"
  | "route_for_approval"
  | "reject"
  | "needs_human";

export type DecisionStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "executed"
  | "failed";

export type Citation = {
  id: string;
  citation_index: number;
  clause_ref: string;
  excerpt: string;
  chunk_id: string | null;
  document_id: string | null;
};

export type Decision = {
  id: string;
  document_id: string;
  extraction_id: string | null;
  outcome: Outcome;
  effective_outcome: Outcome;
  rationale: string;
  unmet_conditions: string[];
  rail_notes: string[];
  rule_id: string | null;
  grounding_passed: boolean;
  grounding_failure: string | null;
  status: DecisionStatus;
  assigned_to: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  override_outcome: Outcome | null;
  override_note: string | null;
  created_at: string;
  citations: Citation[];
  /** What the case is, so a queue row can lead with it. */
  filename: string;
  supplier: string | null;
  amount: string | null;
  currency: string | null;
};

export type ExtractedField = {
  name: string;
  value: string | null;
  source_span: string | null;
  verified: boolean;
};

export type DecisionDetail = Decision & {
  /** The parsed document, exactly as the verbatim check saw it. Every
   *  field's `source_span` is a literal substring of this. */
  document_text: string;
  unverified_fields: string[];
  arithmetic_ok: boolean;
  arithmetic_failures: string[];
  fields: ExtractedField[];
};

export type QueueStats = {
  pending: number;
  executed: number;
  total: number;
  auto_approved: number;
  overridden: number;
  override_rate: number | null;
};

const POLL_MS = 10_000;

/**
 * The review queue. Polls, because decisions arrive from a background
 * worker rather than from anything the reviewer did.
 */
export function useQueue(status: DecisionStatus | null = "pending_review") {
  const query = useQuery({
    queryKey: ["decisions", status],
    queryFn: () =>
      api.get<Decision[]>(
        `/decisions${status ? `?status=${status}` : ""}`,
      ),
    refetchInterval: POLL_MS,
  });
  return { decisions: query.data ?? [], isLoading: query.isLoading };
}

export function useQueueStats() {
  const query = useQuery({
    queryKey: ["decision-stats"],
    queryFn: () => api.get<QueueStats>("/decisions/stats"),
    refetchInterval: POLL_MS,
  });
  return query.data ?? null;
}

export function useDecision(id: string) {
  const query = useQuery({
    queryKey: ["decision", id],
    queryFn: () => api.get<DecisionDetail>(`/decisions/${id}`),
    // A 404 means this decision is not yours or does not exist; retrying
    // will not change that. Anything else is worth one more attempt.
    retry: (count, error) =>
      error instanceof ApiError && error.status === 404 ? false : count < 1,
  });
  return {
    decision: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error as ApiError | Error | null,
  };
}

/**
 * Approve and reject. Both invalidate the queue and the header numbers,
 * because a decision leaving the queue changes both.
 */
export function useReview() {
  const qc = useQueryClient();

  const invalidate = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["decisions"] });
    void qc.invalidateQueries({ queryKey: ["decision-stats"] });
    void qc.invalidateQueries({ queryKey: ["audit"] });
  }, [qc]);

  const approve = useMutation({
    mutationFn: (args: {
      id: string;
      override_outcome?: Outcome;
      note?: string;
    }) =>
      api.post<{ decision_id: string; status: string; event_id: string | null }>(
        `/decisions/${args.id}/approve`,
        { override_outcome: args.override_outcome ?? null, note: args.note ?? null },
      ),
    onSuccess: invalidate,
  });

  const reject = useMutation({
    mutationFn: (args: { id: string; note?: string }) =>
      api.post<{ decision_id: string; status: string }>(
        `/decisions/${args.id}/reject`,
        { note: args.note ?? null },
      ),
    onSuccess: invalidate,
  });

  return {
    approve: approve.mutateAsync,
    reject: reject.mutateAsync,
    isBusy: approve.isPending || reject.isPending,
  };
}
