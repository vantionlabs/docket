"use client";

import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { StatusBadge } from "@/components/decisions/outcome-badge";
import { Badge } from "@/components/ui/badge";
import { API_URL, api } from "@/lib/api";
import type { DecisionStatus } from "@/hooks/use-decisions";

type AuditRow = {
  decision_id: string;
  document_id: string;
  filename: string;
  supplier: string | null;
  amount: string | null;
  currency: string | null;
  outcome: string;
  effective_outcome: string;
  status: DecisionStatus;
  rule_id: string | null;
  grounding_passed: boolean;
  citation_count: number;
  reviewed_by_email: string | null;
  reviewed_at: string | null;
  override_outcome: string | null;
  executed_reference: string | null;
  created_at: string;
};

const STATUSES: (DecisionStatus | "all")[] = [
  "all",
  "pending_review",
  "approved",
  "executed",
  "rejected",
  "failed",
];

/**
 * The audit log. Boring, and the reason a finance director signs.
 *
 * Every decision this org has made, newest first, with the citation count
 * and what the adapter returned. Export is a plain link to the backend so
 * the browser downloads the CSV with the session cookie attached, rather
 * than the page assembling one it would have to keep in sync.
 */
export default function AuditPage() {
  const [status, setStatus] = useState<DecisionStatus | "all">("all");

  const { data, isLoading } = useQuery({
    queryKey: ["audit", status],
    queryFn: () =>
      api.get<AuditRow[]>(
        `/audit${status === "all" ? "" : `?status=${status}`}`,
      ),
  });
  const rows = data ?? [];

  return (
    <div className="flex h-screen flex-col">
      <header className="flex shrink-0 items-center gap-3 border-b px-6 py-4">
        <h1 className="text-lg font-semibold tracking-tight">Audit</h1>
        <div className="flex gap-1">
          {STATUSES.map((option) => (
            <button
              key={option}
              onClick={() => setStatus(option)}
              className={`rounded-md px-2 py-1 text-xs transition-colors ${
                status === option
                  ? "bg-accent font-medium"
                  : "text-muted-foreground hover:bg-accent/50"
              }`}
            >
              {option === "all" ? "All" : option.replace("_", " ")}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <a
          href={`${API_URL}/audit/export.csv${status === "all" ? "" : `?status=${status}`}`}
          className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 text-xs"
        >
          <Download size={13} /> Export CSV
        </a>
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted/50 text-muted-foreground sticky top-0 text-[11px] tracking-wide uppercase">
            <tr>
              <Th>Decided</Th>
              <Th>Document</Th>
              <Th>Supplier</Th>
              <Th className="text-right">Amount</Th>
              <Th>Outcome</Th>
              <Th>Status</Th>
              <Th className="text-right">Clauses</Th>
              <Th>Reviewed by</Th>
              <Th>Executed</Th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {isLoading && (
              <tr>
                <td colSpan={9} className="text-muted-foreground px-4 py-6 text-sm">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && rows.length === 0 && (
              <tr>
                <td colSpan={9} className="text-muted-foreground px-4 py-10 text-sm">
                  Nothing decided yet.
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.decision_id} className="hover:bg-accent/40">
                <Td className="text-muted-foreground whitespace-nowrap text-xs">
                  {new Date(row.created_at).toLocaleDateString()}
                </Td>
                <Td>
                  <Link
                    href={`/decisions/${row.decision_id}`}
                    className="hover:underline"
                  >
                    {row.filename || "document"}
                  </Link>
                </Td>
                <Td className="text-muted-foreground">{row.supplier ?? "—"}</Td>
                <Td className="text-right tabular-nums whitespace-nowrap">
                  {row.amount ? `${row.amount} ${row.currency ?? ""}` : "—"}
                </Td>
                <Td>
                  <span className="text-xs">
                    {row.effective_outcome.replace(/_/g, " ")}
                  </span>
                  {row.override_outcome && (
                    <Badge variant="outline" className="ml-1.5">
                      overridden
                    </Badge>
                  )}
                  {!row.grounding_passed && (
                    <Badge variant="destructive" className="ml-1.5">
                      ungrounded
                    </Badge>
                  )}
                </Td>
                <Td>
                  <StatusBadge status={row.status} />
                </Td>
                <Td className="text-right tabular-nums">{row.citation_count}</Td>
                <Td className="text-muted-foreground text-xs">
                  {row.reviewed_by_email ?? (row.rule_id ? `rule: ${row.rule_id}` : "—")}
                </Td>
                <Td className="text-muted-foreground font-mono text-[11px]">
                  {row.executed_reference ?? "—"}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <th className={`px-4 py-2 font-medium ${className}`}>{children}</th>;
}

function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-4 py-2 ${className}`}>{children}</td>;
}
