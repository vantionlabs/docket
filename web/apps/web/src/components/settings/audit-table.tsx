import { EmptyState } from "@/components/app/empty-state.js";
import { Badge } from "@/components/ui/badge.js";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.js";
import type { AuditEntry, AuditOutcome } from "@forge/domain/iam/Audit";
import { DateTime } from "effect";
import { ScrollText } from "lucide-react";

const variantFor = (outcome: AuditOutcome) =>
  outcome === "ok" ? "secondary" : outcome === "denied" ? "destructive" : "outline";

export const AuditTable = (props: { readonly entries: ReadonlyArray<AuditEntry>; }) => {
  if (props.entries.length === 0) {
    return (
      <EmptyState
        icon={ScrollText}
        title="Nothing recorded yet"
        description="Every change made in this organization is logged here as it happens."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-44">When</TableHead>
          <TableHead>Who</TableHead>
          <TableHead>Action</TableHead>
          <TableHead className="w-28">Outcome</TableHead>
          <TableHead>Detail</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {props.entries.map((entry) => (
          <TableRow key={`${entry.actorEmail}-${DateTime.toEpochMillis(entry.at)}-${entry.action}`}>
            <TableCell>
              <span className="text-muted-foreground font-mono text-xs">
                {DateTime.toDateUtc(entry.at).toISOString().slice(0, 19).replace("T", " ")}
              </span>
            </TableCell>
            <TableCell>
              <div className="min-w-0">
                <p className="truncate text-sm">{entry.actorEmail}</p>
                <p className="text-muted-foreground font-mono text-[10px]">{entry.actorRole}</p>
              </div>
            </TableCell>
            <TableCell>
              <span className="font-mono text-xs">{entry.action}</span>
            </TableCell>
            {
              /* A denial is the most security-relevant row in here, so it is the
                one that stands out rather than being buried in successes. */
            }
            <TableCell>
              <Badge variant={variantFor(entry.outcome)}>{entry.outcome}</Badge>
            </TableCell>
            <TableCell>
              <span className="text-muted-foreground font-mono text-[10px]">{entry.detail}</span>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
