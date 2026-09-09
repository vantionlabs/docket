"use client";

import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Play } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Flip = {
  decision_id: string;
  document_id: string;
  filename: string;
  was: string;
  would_be: string;
  amount: string | null;
  supplier: string | null;
  reason: string;
};

type ReplayResult = {
  considered: number;
  unreplayable: number;
  auto_approved_before: number;
  auto_approved_after: number;
  automation_rate_before: number;
  automation_rate_after: number;
  value_newly_automatic: string;
  newly_automatic: Flip[];
  newly_reviewed: Flip[];
};

type SweepPoint = {
  limit: string;
  automatic: number;
  rate: number;
  newly_automatic: number;
  newly_reviewed: number;
  value_newly_automatic: string;
};

type SweepResult = {
  considered: number;
  unreplayable: number;
  points: SweepPoint[];
};

const LADDER = ["250", "500", "1000", "2500", "5000", "10000", "25000"];

const euros = (value: string | number | null) =>
  value === null
    ? "—"
    : new Intl.NumberFormat("nl-NL", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 0,
      }).format(Number(value));

const percent = (value: number) => `${(value * 100).toFixed(1)}%`;

/**
 * Counterfactual replay: what a rule that does not exist yet would have done.
 *
 * The screen exists because the question it answers is normally answered by
 * intuition. Rail 3 is deterministic and every input it reads was stored at
 * decision time, so the whole history can be re-run against a proposed rule
 * in a second, without calling a model — and the page says so, because a
 * number whose provenance is unclear is one nobody should act on.
 */
export default function ReplayPage() {
  const [limit, setLimit] = useState("2500");
  const [requirePo, setRequirePo] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const replay = useMutation({
    mutationFn: () =>
      api.post<ReplayResult>("/replay", {
        name: "proposed",
        conditions: {
          max_total_incl_vat: limit || "0",
          approved_suppliers: [],
          require_po: requirePo,
        },
      }),
    onError: (e) => setError(e instanceof Error ? e.message : "Replay failed"),
  });

  const sweep = useMutation({
    mutationFn: () =>
      api.post<SweepResult>("/replay/sweep", {
        limits: LADDER,
        require_po: requirePo,
      }),
    onError: (e) => setError(e instanceof Error ? e.message : "Sweep failed"),
  });

  const result = replay.data;
  const curve = sweep.data;
  const peak = curve ? Math.max(...curve.points.map((p) => p.rate), 0.0001) : 1;

  function run() {
    setError(null);
    void replay.mutateAsync();
    void sweep.mutateAsync();
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="text-lg font-semibold tracking-tight">
        Replay a rule against history
      </h1>
      <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
        Re-runs every decision this org has already made against a rule that
        does not exist yet, and shows which ones would land somewhere else.
        Nothing is changed and no model is called: rail 3 is deterministic, so
        the answer is arithmetic over what was recorded at the time.
      </p>

      {/* the proposed rule */}
      <div className="mt-8 flex flex-wrap items-end gap-4 border-y py-6">
        <div className="space-y-1.5">
          <Label htmlFor="limit">Maximum total including VAT</Label>
          <Input
            id="limit"
            inputMode="decimal"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            className="w-44"
          />
        </div>
        <label className="flex h-9 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={requirePo}
            onChange={(e) => setRequirePo(e.target.checked)}
            className="size-4"
          />
          Require a purchase order
        </label>
        <Button
          onClick={run}
          disabled={replay.isPending || sweep.isPending}
          className="gap-2"
        >
          <Play size={14} />
          {replay.isPending || sweep.isPending ? "Replaying…" : "Replay"}
        </Button>
      </div>

      {error && (
        <p className="text-destructive mt-4 text-sm" role="alert">
          {error}
        </p>
      )}

      {result && (
        <>
          {/* what the change is worth */}
          <div className="mt-8 grid gap-px overflow-hidden rounded-md border bg-border sm:grid-cols-3">
            <Figure
              label="Decided without a person"
              value={`${result.auto_approved_after} of ${result.considered}`}
              detail={`${percent(result.automation_rate_before)} → ${percent(
                result.automation_rate_after,
              )}`}
            />
            <Figure
              label="Would stop reaching a reviewer"
              value={String(result.newly_automatic.length)}
              detail={`worth ${euros(result.value_newly_automatic)}`}
            />
            <Figure
              label="Would come back to a reviewer"
              value={String(result.newly_reviewed.length)}
              detail="decisions that are automatic today"
            />
          </div>

          <p className="text-muted-foreground mt-3 text-xs">
            Measured over {result.considered.toLocaleString("nl-NL")} decisions.
            {result.unreplayable > 0 && (
              <>
                {" "}
                {result.unreplayable} more could not be replayed, because what
                the model proposed was not recorded when they were decided.
                They are excluded rather than assumed.
              </>
            )}
          </p>
        </>
      )}

      {/* the curve */}
      {curve && (
        <section className="mt-10">
          <h2 className="text-sm font-medium">
            Automation against the limit
          </h2>
          <p className="text-muted-foreground mt-1 text-xs">
            Every rung evaluated over the same {curve.considered.toLocaleString("nl-NL")}{" "}
            decisions, in one pass. The rails only ever move a decision toward
            a person, so a higher ceiling cannot loosen a grounding failure or
            an unverified field — the curve is the threshold alone.
          </p>

          <ul className="mt-4 space-y-1.5">
            {curve.points.map((point) => (
              <li key={point.limit} className="flex items-center gap-3 text-xs">
                <span className="text-muted-foreground w-20 shrink-0 text-right font-mono tabular-nums">
                  {euros(point.limit)}
                </span>
                <span className="bg-muted relative h-5 flex-1 overflow-hidden rounded-sm">
                  <span
                    className="bg-primary/80 absolute inset-y-0 left-0 rounded-sm transition-[width] duration-500"
                    style={{ width: `${(point.rate / peak) * 100}%` }}
                  />
                </span>
                <span className="w-14 shrink-0 text-right font-mono tabular-nums">
                  {percent(point.rate)}
                </span>
                <span className="text-muted-foreground w-28 shrink-0 text-right font-mono tabular-nums">
                  {euros(point.value_newly_automatic)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* what it would let through, by name */}
      {result && result.newly_automatic.length > 0 && (
        <FlipList
          title="Would stop reaching a reviewer"
          note="These were looked at by a person. Under the proposed rule they would not be."
          tone="warning"
          flips={result.newly_automatic}
        />
      )}

      {result && result.newly_reviewed.length > 0 && (
        <FlipList
          title="Would come back to a reviewer"
          note="These execute automatically today. The proposed rule stops them."
          tone="secondary"
          flips={result.newly_reviewed}
        />
      )}

      {result &&
        result.newly_automatic.length === 0 &&
        result.newly_reviewed.length === 0 && (
          <p className="text-muted-foreground mt-8 text-sm">
            Nothing moves. Every decision lands exactly where it landed, which
            is what a rule already matching current behaviour looks like.
          </p>
        )}
    </div>
  );
}

function Figure({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="bg-background px-4 py-4">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-1 font-mono text-xl tabular-nums">{value}</p>
      <p className="text-muted-foreground mt-0.5 text-xs">{detail}</p>
    </div>
  );
}

function FlipList({
  title,
  note,
  tone,
  flips,
}: {
  title: string;
  note: string;
  tone: "warning" | "secondary";
  flips: Flip[];
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? flips : flips.slice(0, 12);

  return (
    <section className="mt-10">
      <h2 className="flex items-center gap-2 text-sm font-medium">
        {title}
        <Badge variant={tone} className="gap-1">
          {tone === "warning" && <AlertTriangle size={10} />}
          {flips.length}
        </Badge>
      </h2>
      <p className="text-muted-foreground mt-1 text-xs">{note}</p>

      <ul className="mt-3 divide-y border-y text-sm">
        {shown.map((flip) => (
          <li key={flip.decision_id} className="flex items-baseline gap-3 py-2">
            <span className="w-24 shrink-0 text-right font-mono text-xs tabular-nums">
              {euros(flip.amount)}
            </span>
            <Link
              href={`/decisions/${flip.decision_id}`}
              className="min-w-0 flex-1 truncate hover:underline"
            >
              {flip.supplier ?? flip.filename}
            </Link>
            <span className="text-muted-foreground shrink-0 font-mono text-xs">
              {flip.was} → {flip.would_be}
            </span>
          </li>
        ))}
      </ul>

      {flips.length > shown.length && (
        <Button
          variant="ghost"
          size="sm"
          className="mt-2"
          onClick={() => setExpanded(true)}
        >
          Show all {flips.length}
        </Button>
      )}
    </section>
  );
}
