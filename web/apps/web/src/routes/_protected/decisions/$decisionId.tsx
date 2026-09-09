import { approveDecisionAtom, decisionAtom, rejectDecisionAtom } from "@/atom/decision-atoms.js";
import { sessionAtom } from "@/atom/session-atoms.js";
import { QueryError } from "@/components/app/query-error.js";
import { DecisionDetail } from "@/components/decision/decision-detail.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import { DecisionId } from "@forge/domain/decision/DecisionRpc";
import { createFileRoute } from "@tanstack/react-router";
import { AsyncResult } from "effect/unstable/reactivity";

const DecisionRoute = () => {
  const { decisionId } = Route.useParams();
  const decision = useAtomValue(decisionAtom(decisionId));
  const session = useAtomValue(sessionAtom);
  const approve = useAtomSet(approveDecisionAtom);
  const approving = useAtomValue(approveDecisionAtom);
  const reject = useAtomSet(rejectDecisionAtom);
  const rejecting = useAtomValue(rejectDecisionAtom);

  if (AsyncResult.isInitial(decision)) {
    return <p className="text-sm text-muted-foreground">loading…</p>;
  }

  if (AsyncResult.isFailure(decision)) {
    return <QueryError result={decision} subject="this decision" />;
  }

  // Hiding the control the server would refuse anyway. The policy is still what
  // decides -- this only keeps a reviewer from being offered something that
  // cannot work.
  const canOverride = AsyncResult.isSuccess(session)
    && session.value.permissions.includes("decision:edit");

  const id = DecisionId.make(decisionId);

  return (
    <DecisionDetail
      decision={decision.value}
      busy={approving.waiting || rejecting.waiting}
      canOverride={canOverride}
      onApprove={(input) => {
        approve({ id, ...input });
      }}
      onReject={(note) => {
        reject({ id, note });
      }}
    />
  );
};

export const Route = createFileRoute("/_protected/decisions/$decisionId")({
  staticData: { crumb: "Decision" },
  component: DecisionRoute,
});
