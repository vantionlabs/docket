import { approveDecisionAtom, queueAtom, rejectDecisionAtom } from "@/atom/decision-atoms.js";
import { QueryError } from "@/components/app/query-error.js";
import { QueueTable } from "@/components/decision/queue-table.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import type { DecisionId } from "@forge/domain/decision/DecisionRpc";
import { createFileRoute } from "@tanstack/react-router";
import { AsyncResult } from "effect/unstable/reactivity";

const Queue = () => {
  const queue = useAtomValue(queueAtom);
  const approve = useAtomSet(approveDecisionAtom);
  const approving = useAtomValue(approveDecisionAtom);
  const reject = useAtomSet(rejectDecisionAtom);
  const rejecting = useAtomValue(rejectDecisionAtom);

  if (AsyncResult.isInitial(queue)) {
    return <p className="text-sm text-muted-foreground">loading…</p>;
  }

  if (AsyncResult.isFailure(queue)) {
    return <QueryError result={queue} subject="the review queue" />;
  }

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">Review queue</h1>
        <p className="text-sm text-muted-foreground">
          Decisions waiting on a person, oldest first
        </p>
      </div>

      <QueueTable
        decisions={queue.value}
        busy={approving.waiting || rejecting.waiting}
        // Approving from the queue is always agreement: the override needs the
        // detail screen, where the reviewer can see what they are overruling.
        onApprove={(id: DecisionId) => approve({ id, overrideOutcome: null, note: null })}
        onReject={(id: DecisionId) => reject({ id, note: null })}
      />
    </section>
  );
};

export const Route = createFileRoute("/_protected/queue")({
  staticData: { crumb: "Review queue" },
  component: Queue,
});
