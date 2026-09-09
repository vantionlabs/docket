import { Badge } from "@/components/ui/badge.js";
import { Button } from "@/components/ui/button.js";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card.js";
import { Input } from "@/components/ui/input.js";
import { Textarea } from "@/components/ui/textarea.js";
import type { Decision } from "@forge/domain/decision/DecisionRpc";
import { DateTime } from "effect";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import * as React from "react";

/** A labelled figure. Null is rendered as an em dash rather than omitted --
 * "not recorded" is information, and a missing row reads as a bug. */
const Fact = (props: { readonly label: string; readonly value: React.ReactNode; }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-xs text-muted-foreground">{props.label}</span>
    <span className="text-sm">{props.value ?? "—"}</span>
  </div>
);

/**
 * Why one decision came out the way it did.
 *
 * The spec's three panes are the document, the extracted fields and the cited
 * clauses. Only the third exists yet -- `sourceDocument` and `extraction` are
 * still Python's -- so this is the reasoning half: what was decided, what the
 * model proposed before the rails, what it could not satisfy, and which clauses
 * it stood on.
 */
export const DecisionDetail = (props: {
  readonly decision: Decision;
  readonly busy: boolean;
  readonly canOverride: boolean;
  readonly onApprove: (
    input: { readonly overrideOutcome: string | null; readonly note: string | null; },
  ) => void;
  readonly onReject: (note: string | null) => void;
}) => {
  const { decision, busy, canOverride } = props;
  const [override, setOverride] = React.useState("");
  const [note, setNote] = React.useState("");

  const overridden = decision.overrideOutcome !== null;
  const pending = decision.status === "pending_review";

  return (
    <section className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold">{decision.effectiveOutcome}</h1>
            {overridden && (
              <Badge variant="outline" title={`The pipeline decided ${decision.outcome}`}>
                overridden from {decision.outcome}
              </Badge>
            )}
            <Badge variant="secondary">{decision.status}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Decided {DateTime.formatIsoDateUtc(decision.decidedAt)}
            {decision.ruleId !== null && ` · rule ${decision.ruleId}`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {decision.groundingPassed
            ? (
              <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <ShieldCheck size={15} aria-hidden />grounded
              </span>
            )
            : (
              <span
                className="flex items-center gap-1.5 text-sm"
                title={decision.groundingFailure ?? undefined}
              >
                <ShieldAlert size={15} aria-hidden />ungrounded
              </span>
            )}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Rationale</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <p className="text-sm leading-relaxed">{decision.rationale}</p>

              {decision.railNotes.length > 0 && (
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-muted-foreground">
                    Why the rails moved the outcome
                  </span>
                  <ul className="list-disc pl-5 text-sm">
                    {decision.railNotes.map((rail) => <li key={rail}>{rail}</li>)}
                  </ul>
                </div>
              )}

              {decision.unmetConditions.length > 0 && (
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-muted-foreground">
                    Conditions it could not satisfy
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {decision.unmetConditions.map((condition) => (
                      <Badge key={condition} variant="outline" className="font-mono text-[11px]">
                        {condition}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {pending && (
            <Card>
              <CardHeader>
                <CardTitle>Review</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <Textarea
                  placeholder="Note (optional)"
                  value={note}
                  onChange={(event) => {
                    setNote(event.target.value);
                  }}
                />

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      props.onApprove({ overrideOutcome: null, note: note === "" ? null : note });
                    }}
                  >
                    Approve
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busy}
                    onClick={() => {
                      props.onReject(note === "" ? null : note);
                    }}
                  >
                    Reject
                  </Button>
                </div>

                {canOverride
                  ? (
                    <div className="flex flex-col gap-2 border-t pt-4">
                      <span className="text-xs text-muted-foreground">
                        Overrule the pipeline. The original outcome is kept beside yours, which is
                        what makes the override rate mean anything.
                      </span>
                      <div className="flex flex-wrap items-center gap-2">
                        <Input
                          className="max-w-64"
                          placeholder="Outcome, e.g. route_to_cost_centre"
                          value={override}
                          onChange={(event) => {
                            setOverride(event.target.value);
                          }}
                        />
                        <Button
                          type="button"
                          variant="secondary"
                          disabled={busy || override.trim() === ""}
                          onClick={() => {
                            props.onApprove({
                              overrideOutcome: override.trim(),
                              note: note === "" ? null : note,
                            });
                          }}
                        >
                          Approve as this instead
                        </Button>
                      </div>
                    </div>
                  )
                  : (
                    <p className="border-t pt-4 text-xs text-muted-foreground">
                      Overruling the pipeline needs the <code>decision:edit</code> permission.
                    </p>
                  )}
              </CardContent>
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Cited clauses</CardTitle>
            </CardHeader>
            <CardContent>
              {decision.citations.length === 0
                ? (
                  <p className="text-sm text-muted-foreground">
                    No clauses were cited, which is why this decision cannot be approved
                    automatically.
                  </p>
                )
                : (
                  <ol className="flex flex-col gap-3">
                    {decision.citations.map((citation) => (
                      <li key={citation.id} className="flex flex-col gap-1">
                        <span className="font-mono text-xs text-muted-foreground">
                          [{citation.citationIndex}] {citation.clauseRef}
                        </span>
                        <blockquote className="border-l-2 pl-3 text-sm leading-relaxed">
                          {citation.excerpt}
                        </blockquote>
                      </li>
                    ))}
                  </ol>
                )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Provenance</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4">
              <Fact label="Pipeline outcome" value={decision.outcome} />
              <Fact label="Model proposed" value={decision.proposedOutcome} />
              <Fact label="Assigned to" value={decision.assignedTo} />
              <Fact
                label="Coverage"
                value={decision.coverageComplete === null
                  // Null is not the same as checked and clean, and a reviewer
                  // reading "no" would be told something untrue.
                  ? "not checked"
                  : `${decision.coverageComplete ? "complete" : "incomplete"}${
                    decision.coverageRecall === null
                      ? ""
                      : ` · recall ${decision.coverageRecall.toFixed(3)}`
                  }`}
              />
              <Fact
                label="Reviewed"
                value={decision.reviewedAt === null
                  ? "not yet"
                  : DateTime.formatIsoDateUtc(decision.reviewedAt)}
              />
              <Fact label="Override note" value={decision.overrideNote} />
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
};
