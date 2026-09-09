import { getSession } from "@/server/session.js";
import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

/**
 * Auth pages share a centred, viewport-constrained shell.
 *
 * `ssr: "data-only"` rather than `false`, and the distinction is the whole point
 * of this route. `false` skips the branch on the server entirely — `beforeLoad`
 * included — so an already-signed-in visitor would be sent the sign-in form and
 * bounced only once the bundle had run. `"data-only"` runs the data phase on the
 * server and leaves the rendering to the browser, which is exactly the split
 * these pages want.
 *
 * Not rendering them on the server is deliberate: no data is loaded, and the
 * forms cannot be server-rendered anyway — effect-form's `Initialize` sets its
 * ready flag in a `useEffect`, which does not run during SSR, so the field
 * subtree returns `null` there. Rendering the card around that hole gave two
 * paints and a page that looked broken between them.
 */
export const Route = createFileRoute("/auth")({
  ssr: "data-only",
  beforeLoad: async () => {
    const user = await getSession();

    // Signed in already: there is nothing to do here.
    if (user !== null) {
      // oxlint-disable-next-line typescript/only-throw-error
      throw redirect({ to: "/" });
    }
  },
  component: () => (
    <div className="flex-1 min-h-0 overflow-auto grid place-items-center p-8">
      <Outlet />
    </div>
  ),
});
