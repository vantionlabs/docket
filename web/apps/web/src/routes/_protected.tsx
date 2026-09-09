import { AppShell } from "@/components/app/app-shell.js";
import { getSession } from "@/server/session.js";
import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

/**
 * Everything behind a session, gated before the page renders.
 *
 * A pathless layout, so nesting under it costs a route nothing in its URL. The
 * session is resolved on the server during SSR and the redirect is decided there
 * too — which is the whole point of the move: the signed-out case never reaches
 * the browser as a flash of application chrome.
 *
 * This is navigation UX, not the security boundary. Every RPC still runs through
 * `AuthMiddleware` on the server, and has to: a `beforeLoad` guard protects the
 * page, not the data behind it.
 */
export const Route = createFileRoute("/_protected")({
  beforeLoad: async () => {
    const user = await getSession();

    if (user === null) {
      // oxlint-disable-next-line typescript/only-throw-error
      throw redirect({ to: "/auth/sign-in" });
    }

    return { user };
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
});
