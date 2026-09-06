import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { getServerUser } from "@/lib/server-auth";

/**
 * Server-side auth guard for the whole authenticated area. The session is
 * checked on the server (getServerUser → backend /users/me) BEFORE any
 * protected page renders; signed-out visitors are redirected without ever
 * receiving protected markup or JS. Data inside the area stays CSR
 * (TanStack Query).
 */
export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getServerUser();
  if (!user) redirect("/sign-in");

  return <AppShell user={user}>{children}</AppShell>;
}
