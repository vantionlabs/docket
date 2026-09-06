import "server-only";

import { headers } from "next/headers";

import { API_URL } from "@/lib/api";
import type { User } from "@/lib/auth-client";

/**
 * Server-side session check. Runs in Server Components (and the auth
 * layouts) BEFORE any protected UI renders: it reads the incoming httpOnly
 * auth cookie and forwards it to the backend's /users/me. Verification
 * stays entirely in the backend — the Next server never sees the secret.
 *
 * Returns the user, or null when signed out.
 */
export async function getServerUser(): Promise<User | null> {
  const cookie = (await headers()).get("cookie");
  if (!cookie) return null;
  try {
    const res = await fetch(`${API_URL}/users/me`, {
      headers: { cookie },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as User;
  } catch {
    return null; // backend unreachable → treat as signed out
  }
}
