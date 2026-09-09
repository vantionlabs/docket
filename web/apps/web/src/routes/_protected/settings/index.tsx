import { createFileRoute, redirect } from "@tanstack/react-router";

/**
 * `/settings` has no page of its own; General is the landing tab.
 *
 * `redirect()` is TanStack Router's control-flow signal, which it expects to be
 * thrown — it is not an error, which is why this is an exception to the rule
 * that only errors are thrown.
 */
export const Route = createFileRoute("/_protected/settings/")({
  beforeLoad: () => {
    // oxlint-disable-next-line typescript/only-throw-error
    throw redirect({ to: "/settings/general" });
  },
});
