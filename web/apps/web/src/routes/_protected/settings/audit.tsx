import { auditLogAtom } from "@/atom/organization-atoms.js";
import { QueryError } from "@/components/app/query-error.js";
import { AuditTable } from "@/components/settings/audit-table.js";
import { Skeleton } from "@/components/ui/skeleton.js";
import { useAtomValue } from "@effect/atom-react";
import { createFileRoute } from "@tanstack/react-router";
import { AsyncResult } from "effect/unstable/reactivity";

const Audit = () => {
  const entries = useAtomValue(auditLogAtom);

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-base font-semibold">Audit log</h2>
        <p className="text-muted-foreground text-sm">
          Every change made in this organization, and every attempt that was refused. Recorded
          centrally, so a new capability is covered without anybody remembering to log it.
        </p>
      </div>

      {AsyncResult.isInitial(entries)
        ? <Skeleton className="h-64 w-full" />
        : AsyncResult.isFailure(entries)
        ? <QueryError result={entries} subject="the audit log" />
        : <AuditTable entries={entries.value} />}
    </section>
  );
};

export const Route = createFileRoute("/_protected/settings/audit")({
  staticData: { crumb: "Audit log" },
  component: Audit,
});
