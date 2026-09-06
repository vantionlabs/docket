import { redirect } from "next/navigation";

import { getServerUser } from "@/lib/server-auth";

/**
 * Auth pages (sign-in / sign-up). Server-side: an already-authenticated
 * visitor is redirected to the app before the form renders.
 */
export default async function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getServerUser();
  if (user) redirect("/");
  return children;
}
