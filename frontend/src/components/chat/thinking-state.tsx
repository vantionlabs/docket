"use client";

import { Check, Loader2, RefreshCw, Search, ShieldCheck } from "lucide-react";

/**
 * What the model is doing right now, in the model's own words.
 *
 * Pattern from Beautiful UI (beautifului.dev, MIT, © 2026 Shane Levine),
 * implemented here: the library is a showcase rather than a distributable
 * package, so this follows its thinking-state design rather than importing it.
 *
 * The backend already emits a stage per turn (`analyzing`, `verifying`,
 * `retrying`, `streaming`) and the old UI threw all of it away for a
 * generic "Thinking…". `retrying` is the one that matters: it means the
 * answer failed grounding and the pipeline is having another go, which is
 * the difference between "this is slow" and "this is being careful".
 */

export type Stage = "analyzing" | "verifying" | "retrying" | "streaming";

const STAGES: Record<Stage, { label: string; icon: React.ElementType }> = {
  analyzing: { label: "Reading your documents", icon: Search },
  verifying: { label: "Checking the answer against its sources", icon: ShieldCheck },
  retrying: { label: "That answer did not check out. Trying again", icon: RefreshCw },
  streaming: { label: "Writing", icon: Check },
};

export function ThinkingState({ stage }: { stage: Stage | null }) {
  if (!stage || stage === "streaming") return null;
  const { label, icon: Icon } = STAGES[stage];
  const isRetry = stage === "retrying";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`mt-4 flex w-fit items-center gap-2.5 rounded-full border px-3 py-1.5 text-xs ${
        isRetry
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "bg-card text-muted-foreground"
      }`}
    >
      <span className="relative flex size-3.5 shrink-0 items-center justify-center">
        <Loader2 size={14} className="absolute animate-spin opacity-40" />
        <Icon size={9} />
      </span>
      {label}
      <span className="inline-flex gap-0.5" aria-hidden>
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-1 animate-bounce rounded-full bg-current opacity-50"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
    </div>
  );
}
