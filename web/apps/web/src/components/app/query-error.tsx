import { Alert, AlertDescription } from "@/components/ui/alert.js";
import { Cause } from "effect";
import type { AsyncResult } from "effect/unstable/reactivity";
import { Lock, TriangleAlert } from "lucide-react";

/**
 * Why a query did not load.
 *
 * The distinction this exists to make: a policy refusal and a server fault are
 * not the same thing, and every page used to report both as "You do not have
 * permission". That is how a missing table read as an access-control decision —
 * the handlers turn unexpected failures into defects, the atom reports a failure
 * either way, and the page guessed.
 *
 * `hasFails` is the test: a typed error reached the error channel deliberately,
 * whereas a defect is something nobody planned for. Only the former is a claim
 * worth making to the user about their permissions.
 */
export const QueryError = (props: {
  readonly result: AsyncResult.Failure<unknown, unknown>;
  /** What could not be loaded, lower case: "keys", "members", "the audit log". */
  readonly subject: string;
}) => {
  const refused = Cause.hasFails(props.result.cause);

  return (
    <Alert>
      {refused
        ? <Lock className="size-4" aria-hidden />
        : <TriangleAlert className="size-4" aria-hidden />}
      <AlertDescription>
        {refused
          ? `Your role does not allow you to see ${props.subject}.`
          : `Could not load ${props.subject}. This is a fault on our side, not a permission problem — try again, and if it persists the server log has the detail.`}
      </AlertDescription>
    </Alert>
  );
};
