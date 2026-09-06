/**
 * Auth client for the FastAPI backend (fastapi-users).
 *
 * The backend owns identity and returns the session as a httpOnly cookie.
 * These calls send `credentials: "include"` so the browser stores/sends the
 * cookie; no token is ever visible to JavaScript.
 */

import { API_URL } from "@/lib/api";

export type User = { id: string; email: string; is_active: boolean };

export async function register(email: string, password: string): Promise<void> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(detailMessage(body.detail) ?? "Registration failed");
  }
}

export async function login(email: string, password: string): Promise<void> {
  // fastapi-users' JWT login is an OAuth2 password flow: form-encoded, with
  // the email in the `username` field. The response sets the httpOnly cookie.
  const form = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API_URL}/auth/jwt/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  if (!res.ok) throw new Error("Invalid email or password");
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/auth/jwt/logout`, {
    method: "POST",
    credentials: "include",
  }).catch(() => {});
}

export async function fetchCurrentUser(): Promise<User | null> {
  const res = await fetch(`${API_URL}/users/me`, { credentials: "include" });
  if (!res.ok) return null;
  return (await res.json()) as User;
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "reason" in detail) {
    return String((detail as { reason: unknown }).reason);
  }
  return null;
}
