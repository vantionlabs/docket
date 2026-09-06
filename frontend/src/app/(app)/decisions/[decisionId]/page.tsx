"use client";

import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CircleAlert,
  Quote,
  ShieldCheck,
  ShieldX,
  X,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { DocumentView } from "@/components/decisions/document-view";
import { OutcomeBadge, StatusBadge } from "@/components/decisions/outcome-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDecision, useReview } from "@/hooks/use-decisions";
import { ApiError } from "@/lib/api";

/**
 * The decision detail screen. Spec section 15 calls this the demo, and the
 * job it has to do is make the check take five seconds: if a reviewer has
 * to re-read the invoice to trust the decision, nothing was saved.
 *
 * So the three panes answer three questions in reading order. What does the
 * document say (left). What did we read off it, and can we prove each value
 * came from the page (middle). Which written rule says this is the right
 * call (right). Clicking a field highlights its span on the left; that link
 * between a number and the words it came from is the whole product.
 */
export default function DecisionDetailPage() {
  const { decisionId } = useParams<{ decisionId: string }>();
  const router = useRouter();
  const { decision, isLoading, error: loadError } = useDecision(decisionId);
  const { approve, reject, isBusy } = useReview();
  const [selectedSpan, setSelectedSpan] = useState<string | null>(null);
  const [selectedField, setSelectedField] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return <p className="text-muted-foreground p-8 text-sm">Loading…</p>;
  }
  if (!decision) {
    // A failure to load is not the same as a decision that is not there.
    // Showing "Not found" for both hid a 500 for longer than it should have.
    const notFound = loadError instanceof ApiError && loadError.status === 404;
    return (
      <div className="p-8">
        <p className="text-sm font-medium">
          {notFound ? "Decision not found." : "Could not load this decision."}
        </p>
        {!notFound && loadError && (
          <p className="text-muted-foreground mt-1 text-sm">
            {loadError.message}
          </p>
        )}
        <Link
          href="/queue"
          className="text-muted-foreground hover:text-foreground mt-3 inline-block text-sm underline"
        >
          Back to the queue
        </Link>
      </div>
    );
  }

  const pending = decision.status === "pending_review";

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      router.push("/queue");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header: what this is, and what happens to it */}
      <header className="flex shrink-0 items-center gap-3 border-b px-6 py-3">
        <Link
          href="/queue"
          className="text-muted-foreground hover:text-foreground"
          aria-label="Back to the queue"
        >
          <ArrowLeft size={16} />
        </Link>
        <h1 className="truncate text-sm font-semibold">
          {decision.supplier ?? decision.filename}
        </h1>
        {decision.amount && (
          <span className="text-muted-foreground shrink-0 text-sm tabular-nums">
            {decision.amount} {decision.currency ?? ""}
          </span>
        )}
        <OutcomeBadge outcome={decision.effective_outcome} />
        <StatusBadge status={decision.status} />
        {decision.rule_id && (
          <Badge variant="outline">rule: {decision.rule_id}</Badge>
        )}
        <div className="flex-1" />
        {pending && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={isBusy}
              onClick={() => void act(() => reject({ id: decision.id }))}
            >
              <X size={14} /> Reject
            </Button>
            <Button
              size="sm"
              disabled={isBusy}
              onClick={() => void act(() => approve({ id: decision.id }))}
            >
              <Check size={14} /> Approve
            </Button>
          </div>
        )}
      </header>

      {error && (
        <p className="text-destructive border-b bg-red-50 px-6 py-2 text-sm">
          {error}
        </p>
      )}

      {/* Why this landed here. The first thing a reviewer needs. */}
      {decision.rail_notes.length > 0 && (
        <div className="shrink-0 border-b bg-amber-50 px-6 py-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-amber-900">
            <AlertTriangle size={13} /> Why this needs you
          </p>
          {/* The rail notes already say this in words a reviewer can act on.
              The raw failure string is precise, written for whoever debugs
              the pipeline, and saying both means saying it twice with the
              worse one first. It lives under the reasoning disclosure. */}
          <ul className="mt-1 space-y-0.5">
            {decision.rail_notes.map((note) => (
              <li key={note} className="text-xs text-amber-800">
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-px overflow-hidden bg-border lg:grid-cols-[1.1fr_1fr_1fr]">
        {/* Left: the document */}
        <section className="bg-background min-h-0 overflow-auto p-4">
          <PaneTitle>Document</PaneTitle>
          <DocumentView text={decision.document_text} highlight={selectedSpan} />
        </section>

        {/* Middle: what we read, and whether we can prove it */}
        <section className="bg-background min-h-0 overflow-auto p-4">
          <PaneTitle>
            Extracted
            {decision.unverified_fields.length > 0 && (
              <Badge variant="destructive" className="ml-2">
                {decision.unverified_fields.length} unverified
              </Badge>
            )}
          </PaneTitle>

          {!decision.arithmetic_ok && (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-2.5">
              <p className="flex items-center gap-1.5 text-xs font-medium text-red-900">
                <CircleAlert size={13} /> The arithmetic does not check out
              </p>
              <ul className="mt-1 space-y-0.5">
                {decision.arithmetic_failures.map((failure) => (
                  <li key={failure} className="text-xs text-red-800">
                    {failure}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <ul className="space-y-px">
            {decision.fields.map((field) => {
              const active = selectedField === field.name;
              return (
                <li key={field.name}>
                  <button
                    onClick={() => {
                      setSelectedField(active ? null : field.name);
                      setSelectedSpan(active ? null : field.source_span);
                    }}
                    disabled={!field.source_span}
                    className={`w-full rounded-md px-2 py-1.5 text-left transition-colors ${
                      active ? "bg-accent" : "hover:bg-accent/50"
                    } disabled:cursor-default disabled:opacity-60`}
                  >
                    <div className="flex items-baseline gap-2">
                      <span className="text-muted-foreground w-32 shrink-0 truncate font-mono text-[11px]">
                        {field.name}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {field.value ?? (
                          <span className="text-muted-foreground italic">
                            not stated
                          </span>
                        )}
                      </span>
                      {field.value !== null &&
                        (field.verified ? (
                          <ShieldCheck
                            size={13}
                            className="shrink-0 text-emerald-600"
                            aria-label="Source span verified in the document"
                          />
                        ) : (
                          <ShieldX
                            size={13}
                            className="text-destructive shrink-0"
                            aria-label="Source span not found in the document"
                          />
                        ))}
                    </div>
                    {active && field.source_span && (
                      <p className="text-muted-foreground mt-1 pl-34 font-mono text-[11px]">
                        &ldquo;{field.source_span}&rdquo;
                      </p>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        {/* Right: the written rule that justifies the call */}
        <section className="bg-background min-h-0 overflow-auto p-4">
          <PaneTitle>Policy</PaneTitle>

          {decision.rationale && (
            <details className="group mb-3">
              <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-xs">
                Show the model&rsquo;s reasoning
              </summary>
              <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
                {decision.rationale}
              </p>
              {decision.grounding_failure && (
                <p className="text-muted-foreground mt-1.5 font-mono text-[11px]">
                  grounding: {decision.grounding_failure}
                </p>
              )}
            </details>
          )}

          {decision.citations.length === 0 && (
            <p className="text-muted-foreground text-xs">
              No policy clause was cited. Nothing here may execute on its own.
            </p>
          )}

          <ol className="space-y-2">
            {decision.citations.map((citation) => (
              <li
                key={citation.id}
                className="bg-card rounded-lg border p-2.5"
              >
                <p className="flex items-center gap-1.5 text-xs font-medium">
                  <Quote size={11} className="text-muted-foreground shrink-0" />
                  [{citation.citation_index}] {citation.clause_ref}
                </p>
                <blockquote className="text-muted-foreground mt-1 border-l-2 pl-2 text-xs leading-relaxed">
                  {citation.excerpt}
                </blockquote>
              </li>
            ))}
          </ol>

          {decision.unmet_conditions.length > 0 && (
            <div className="mt-4">
              <PaneTitle>Unmet conditions</PaneTitle>
              <ul className="space-y-1">
                {decision.unmet_conditions.map((condition) => (
                  <li
                    key={condition}
                    className="text-muted-foreground flex gap-1.5 text-xs"
                  >
                    <span aria-hidden>&middot;</span>
                    {condition}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {decision.assigned_to && (
            <p className="text-muted-foreground mt-4 text-xs">
              Suggested approver: {decision.assigned_to}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

function PaneTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-muted-foreground mb-2 flex items-center text-[11px] font-medium tracking-wide uppercase">
      {children}
    </h2>
  );
}
