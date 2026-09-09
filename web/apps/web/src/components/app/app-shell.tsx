import { sessionAtom } from "@/atom/session-atoms.js";
import { Breadcrumbs } from "@/components/app/breadcrumbs.js";
import { CommandPalette } from "@/components/app/command-palette.js";
import { Sidebar } from "@/components/app/sidebar.js";
import { VerifyEmailBanner } from "@/components/auth/verify-email-banner.js";
import { useAtomRefresh } from "@effect/atom-react";
import { useNavigate, useRouteContext } from "@tanstack/react-router";
import type * as React from "react";

/**
 * Signed-in chrome: fixed sidebar, scrolling content pane.
 *
 * No session gate of its own any more. `/_protected` resolves the session on the
 * server and redirects there, so by the time this renders there is a user — which
 * is why it reads one out of route context instead of waiting on an atom and
 * showing a "checking…" state the server already knew the answer to.
 *
 * The session atom is still refreshed on sign-out, because the RPC client caches
 * the identity for everything else on the page.
 */
export const AppShell = (props: { readonly children: React.ReactNode; }) => {
  const { user } = useRouteContext({ from: "/_protected" });
  const refresh = useAtomRefresh(sessionAtom);
  const navigate = useNavigate();

  return (
    <div className="flex min-h-0 flex-1">
      <CommandPalette />
      <Sidebar
        email={user.email}
        onSignOut={() => {
          refresh();
          void navigate({ to: "/auth/sign-in" });
        }}
      />
      <div className="flex min-w-0 flex-1 flex-col overflow-auto">
        {!user.emailVerified && (
          <div className="p-4 pb-0">
            <VerifyEmailBanner email={user.email} />
          </div>
        )}
        {
          /*
          Breadcrumb row, then the page. Mounted here rather than pasted into a
          dozen route files, so a new page gets a trail by declaring a `crumb`
          and nothing else.
        */
        }
        <main className="flex min-h-0 flex-1 flex-col gap-4 p-8">
          <Breadcrumbs />
          {props.children}
        </main>
      </div>
    </div>
  );
};
