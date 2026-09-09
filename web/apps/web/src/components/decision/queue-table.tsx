import { EmptyState } from "@/components/app/empty-state.js";
import { Badge } from "@/components/ui/badge.js";
import { Button } from "@/components/ui/button.js";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.js";
import type { DecisionId, DecisionSummary } from "@forge/domain/decision/DecisionRpc";
import { Link } from "@tanstack/react-router";
import { DateTime } from "effect";
import { Check, Inbox, ShieldAlert, X } from "lucide-react";
import * as React from "react";

/** A key hint in the header, so the shortcuts are discoverable without a manual. */
const Key = (props: { readonly children: string; }) => (
  <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] leading-none">
    {props.children}
  </kbd>
);

/**
 * The review queue.
 *
 * Keyboard-first on purpose: a reviewer clearing forty invoices should never
 * have to reach for the mouse. `j` and `k` move, `a` approves, `r` rejects.
 * Approving here is always agreement -- overruling the pipeline is a different
 * capability and belongs on the decision detail screen, where the reviewer can
 * see what they are disagreeing with.
 */
export const QueueTable = (props: {
  readonly decisions: ReadonlyArray<DecisionSummary>;
  readonly busy: boolean;
  readonly onApprove: (id: DecisionId) => void;
  readonly onReject: (id: DecisionId) => void;
  readonly onOpen: (id: DecisionId) => void;
}) => {
  const [selected, setSelected] = React.useState(0);
  const rows = React.useRef<Array<HTMLTableRowElement | null>>([]);

  const { decisions, busy, onApprove, onReject, onOpen } = props;
  // Clamped rather than stored, so a row leaving the queue under the cursor
  // cannot leave the selection pointing past the end.
  const index = decisions.length === 0 ? 0 : Math.min(selected, decisions.length - 1);

  const move = React.useCallback((delta: number) => {
    setSelected((current) => Math.max(0, Math.min(current + delta, decisions.length - 1)));
  }, [decisions.length]);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // Never steal a keystroke meant for a field, and leave browser and OS
      // shortcuts alone.
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("input, textarea, [contenteditable]")) {
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const current = decisions[index];

      switch (event.key) {
        case "j":
          move(1);
          break;
        case "k":
          move(-1);
          break;
        case "a":
          if (current !== undefined && !busy) onApprove(current.id);
          break;
        case "r":
          if (current !== undefined && !busy) onReject(current.id);
          break;
        case "Enter":
          if (current !== undefined) onOpen(current.id);
          break;
        default:
          return;
      }

      event.preventDefault();
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [decisions, index, busy, move, onApprove, onReject, onOpen]);

  React.useEffect(() => {
    rows.current[index]?.scrollIntoView({ block: "nearest" });
  }, [index]);

  if (decisions.length === 0) {
    return (
      <EmptyState
        icon={Inbox}
        title="Nothing waiting"
        description="Every decision has been reviewed. New documents land here once the pipeline has read them."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Key>j</Key>
        <Key>k</Key> move
        <Key>a</Key> approve
        <Key>r</Key> reject
        <Key>↵</Key> open
      </p>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Outcome</TableHead>
              <TableHead>Assigned to</TableHead>
              <TableHead>Grounded</TableHead>
              <TableHead>Decided</TableHead>
              <TableHead className="w-32" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {decisions.map((decision, row) => (
              <TableRow
                key={decision.id}
                ref={(element) => {
                  rows.current[row] = element;
                }}
                aria-selected={row === index}
                className={row === index ? "bg-muted/60" : undefined}
                onClick={() => setSelected(row)}
              >
                <TableCell>
                  <Link
                    to="/decisions/$decisionId"
                    params={{ decisionId: decision.id }}
                    className="rounded-sm focus-visible:ring-2 focus-visible:outline-none"
                  >
                    <Badge variant="secondary">{decision.effectiveOutcome}</Badge>
                  </Link>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {decision.assignedTo ?? "—"}
                </TableCell>
                <TableCell>
                  {decision.groundingPassed
                    ? <span className="text-sm text-muted-foreground">yes</span>
                    : (
                      <span className="flex items-center gap-1 text-sm">
                        <ShieldAlert size={13} aria-hidden />
                        <span>ungrounded</span>
                      </span>
                    )}
                </TableCell>
                <TableCell className="text-sm tabular-nums text-muted-foreground">
                  {DateTime.formatIsoDateUtc(decision.decidedAt)}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      aria-label="Approve"
                      onClick={() => onApprove(decision.id)}
                    >
                      <Check size={14} aria-hidden />
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      aria-label="Reject"
                      onClick={() => onReject(decision.id)}
                    >
                      <X size={14} aria-hidden />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};
