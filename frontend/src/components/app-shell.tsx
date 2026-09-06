"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { ThreadSidebar } from "@/components/chat/thread-sidebar";
import { logout, type User } from "@/lib/auth-client";

/**
 * Client chrome for the authenticated area. The auth GUARD is server-side
 * (see (app)/layout.tsx) — this component only renders once the server has
 * confirmed a session and passed the user down, so there is no loading
 * flash and no protected markup ever reaches a signed-out visitor.
 */
export function AppShell({
  user,
  children,
}: {
  user: User;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();

  async function onSignOut() {
    await logout();
    // The cookie is cleared; navigating re-runs the server guard.
    router.replace("/sign-in");
  }

  return (
    <div className="flex min-h-screen">
      <aside className="bg-card flex w-64 shrink-0 flex-col border-r">
        <div className="flex items-center justify-between px-4 py-4">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            AI Project
          </Link>
          <button
            onClick={onSignOut}
            className="text-muted-foreground hover:text-foreground text-xs transition-colors"
          >
            Sign out
          </button>
        </div>
        <nav className="px-2">
          <Link
            href="/documents"
            className={`block rounded-lg px-2 py-1.5 text-sm transition-colors ${
              pathname === "/documents"
                ? "bg-accent font-medium"
                : "text-muted-foreground hover:bg-accent/50"
            }`}
          >
            Documents
          </Link>
        </nav>
        <div className="mt-4 min-h-0 flex-1 overflow-y-auto border-t px-2 pt-3">
          <ThreadSidebar activePath={pathname} />
        </div>
        <div className="text-muted-foreground border-t px-4 py-3 text-xs">
          {user.email}
        </div>
      </aside>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
