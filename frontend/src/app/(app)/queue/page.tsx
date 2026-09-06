"use client";

import { Check, Keyboard, ShieldX, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { OutcomeBadge } from "@/components/decisions/outcome-badge";
import { Badge } from "@/components/ui/badge";
import { useQueue, useQueueStats, useReview } from "@/hooks/use-decisions";

/**
 * The review queue. This is the product.
 *
 * Keyboard-first on purpose: a reviewer clearing forty invoices should
 * never touch the mouse. j/k move, a approves, r rejects, Enter opens the
 * detail screen. The selected row stays scrolled into view so the hands
 * never have to leave the keys to find where they are.
 */
export default function QueuePage() {
  const router = useRouter();
  const { decisions, isLoading } = useQueue("pending_review");
  const stats = useQueueStats();
  const { approve, reject, isBusy } = useReview();
  const [cursor, setCursor] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const rowRefs = useRef<(HTMLLIElement | null)[]>([]);

  // Keep the cursor inside the list as decisions leave it.
  const bounded = Math.min(cursor, Math.max(decisions.length - 1, 0));

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
      setError(null);
      try {
        await fn();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong");
      }
    },
    [],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const current = decisions[bounded];
      switch (event.key) {
        case "j":
        case "ArrowDown":
          event.preventDefault();
          setCursor((c) => Math.min(c + 1, decisions.length - 1));
          break;
        case "k":
        case "ArrowUp":
          event.preventDefault();
          setCursor((c) => Math.max(c - 1, 0));
          break;
        case "Enter":
          if (current) router.push(`/decisions/${current.id}`);
          break;
        case "a":
          if (current && !isBusy) void act(() => approve({ id: current.id }));
          break;
        case "r":
          if (current && !isBusy) void act(() => reject({ id: current.id }));
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [decisions, bounded, isBusy, approve, reject, router, act]);

  useEffect(() => {
    rowRefs.current[bounded]?.scrollIntoView({ block: "nearest" });
  }, [bounded]);

  return (
    <div className="flex h-screen flex-col">
      <header className="shrink-0 border-b px-6 py-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold tracking-tight">Queue</h1>
          <span className="text-muted-foreground text-xs">
            oldest first
          </span>
          <div className="flex-1" />
          <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
            <Keyboard size={13} />
            <Key>j</Key>
            <Key>k</Key> move
            <Key>a</Key> approve
            <Key>r</Key> reject
            <Key>&crarr;</Key> open
          </p>
        </div>

        {/* The numbers that prove the thing works (spec section 15). */}
        {stats && (
          <dl className="mt-3 flex gap-6">
            <Stat label="Pending" value={stats.pending} />
            <Stat label="Executed" value={stats.executed} />
            <Stat
              label="Auto-approved"
              value={
                stats.total
                  ? `${Math.round((stats.auto_approved / stats.total) * 100)}%`
                  : "—"
              }
            />
            <Stat
              label="Override rate"
              value={
                stats.override_rate === null
                  ? "—"
                  : `${Math.round(stats.override_rate * 100)}%`
              }
              hint="How often a reviewer disagreed. This is what tells you when a threshold can widen."
            />
          </dl>
        )}
      </header>

      {error && (
        <p className="text-destructive border-b bg-red-50 px-6 py-2 text-sm">
          {error}
        </p>
      )}

      <ul className="min-h-0 flex-1 divide-y overflow-auto">
        {isLoading && (
          <li className="text-muted-foreground px-6 py-6 text-sm">Loading…</li>
        )}
        {!isLoading && decisions.length === 0 && (
          <li className="text-muted-foreground px-6 py-10 text-sm">
            Nothing waiting. Decisions arrive here when a document has been
            checked against policy and needs a person.
          </li>
        )}
        {decisions.map((decision, index) => {
          const selected = index === bounded;
          return (
            <li
              key={decision.id}
              ref={(el) => {
                rowRefs.current[index] = el;
              }}
              onMouseEnter={() => setCursor(index)}
              onClick={() => router.push(`/decisions/${decision.id}`)}
              className={`flex cursor-pointer items-center gap-3 px-6 py-3 transition-colors ${
                selected ? "bg-accent" : "hover:bg-accent/40"
              }`}
            >
              <span
                aria-hidden
                className={`h-8 w-0.5 shrink-0 rounded-full ${
                  selected ? "bg-foreground" : "bg-transparent"
                }`}
              />
              {/* What the case is comes first. Why it stalled comes second:
                  a reviewer recognises "Fabrikam, EUR 12,196.80" and cannot
                  act on "grounding failed". */}
              <div className="min-w-0 flex-1">
                <p className="flex items-baseline gap-2 text-sm">
                  <span className="truncate font-medium">
                    {decision.supplier ?? decision.filename ?? "Decision"}
                  </span>
                  {decision.amount && (
                    <span className="text-muted-foreground shrink-0 tabular-nums">
                      {decision.amount} {decision.currency ?? ""}
                    </span>
                  )}
                </p>
                <p className="text-muted-foreground mt-0.5 truncate text-xs">
                  {decision.rail_notes[0] ??
                    `${decision.citations.length} clause${
                      decision.citations.length === 1 ? "" : "s"
                    } cited`}
                </p>
              </div>
              <span className="text-muted-foreground hidden shrink-0 text-xs tabular-nums xl:block">
                {new Date(decision.created_at).toLocaleDateString()}
              </span>

              {!decision.grounding_passed && (
                <Badge variant="destructive" className="gap-1">
                  <ShieldX size={11} /> ungrounded
                </Badge>
              )}
              <OutcomeBadge outcome={decision.effective_outcome} />

              <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 has-[:focus]:opacity-100">
                <IconAction
                  label="Approve"
                  onClick={() => void act(() => approve({ id: decision.id }))}
                  disabled={isBusy}
                >
                  <Check size={14} />
                </IconAction>
                <IconAction
                  label="Reject"
                  onClick={() => void act(() => reject({ id: decision.id }))}
                  disabled={isBusy}
                >
                  <X size={14} />
                </IconAction>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div title={hint}>
      <dt className="text-muted-foreground text-[11px] tracking-wide uppercase">
        {label}
      </dt>
      <dd className="text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Key({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="bg-muted rounded border px-1 font-mono text-[10px]">
      {children}
    </kbd>
  );
}

function IconAction({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      aria-label={label}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="text-muted-foreground hover:bg-background hover:text-foreground rounded-md p-1.5 transition-colors disabled:opacity-40"
    >
      {children}
    </button>
  );
}
