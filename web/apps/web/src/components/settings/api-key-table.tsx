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
import { KEY_PREFIX } from "@forge/domain/iam/ApiKey";
import type { ApiKey } from "@forge/domain/iam/ApiKey";
import { DateTime } from "effect";
import { KeyRound } from "lucide-react";

const lastUsed = (at: ApiKey["lastUsedAt"]) =>
  at === null
    ? <span className="text-muted-foreground text-sm">never</span>
    : (
      <span className="text-muted-foreground text-xs">
        {DateTime.toDateUtc(at).toISOString().slice(0, 16).replace("T", " ")}
      </span>
    );

export const ApiKeyTable = (props: {
  readonly keys: ReadonlyArray<ApiKey>;
  readonly onRevoke: (id: string) => void;
}) => {
  if (props.keys.length === 0) {
    return (
      <EmptyState
        icon={KeyRound}
        title="No keys yet"
        description="Create one to call the app without a browser session."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead className="w-32">Acts as</TableHead>
          <TableHead className="w-40">Last used</TableHead>
          <TableHead className="w-24" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {props.keys.map((key) => (
          <TableRow key={key.id}>
            <TableCell>
              <div className="min-w-0">
                <p className="truncate font-medium">{key.name}</p>
                {/* The prefix and hint together are what makes a leaked key findable. */}
                <p className="text-muted-foreground font-mono text-[10px]">
                  {KEY_PREFIX}
                  {key.hint}…
                </p>
              </div>
            </TableCell>
            <TableCell>
              <Badge variant="secondary" className="font-mono text-xs">{key.role}</Badge>
            </TableCell>
            <TableCell>{lastUsed(key.lastUsedAt)}</TableCell>
            <TableCell className="text-right">
              <Button variant="ghost" size="sm" onClick={() => props.onRevoke(key.id)}>
                Revoke
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
