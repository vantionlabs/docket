import { resolveSession } from "@/server/session.js";
import { createAuthClient } from "better-auth/react";
import { describe, expect, it, vi } from "vitest";

const user = { id: "u1", email: "a@example.com", emailVerified: true, name: "A" };

/**
 * A real client whose transport is stubbed, rather than a stubbed client.
 *
 * `customFetchImpl` is better-auth's own seam, so what is under test is the real
 * client — its URL building, its cookie forwarding and its error handling —
 * rather than a hand-written stand-in that could agree with a wrong assumption.
 *
 * Built here rather than imported: the app's client resolves its base URL per
 * bundle, and a test asserting on the request needs one it named itself.
 */
const clientResponding = (init: { status?: number; body?: unknown; }) => {
  const fetchImpl = vi.fn(() =>
    Promise.resolve(
      new Response(init.body === undefined ? "" : JSON.stringify(init.body), {
        status: init.status ?? 200,
        headers: { "content-type": "application/json" },
      }),
    )
  );

  const client = createAuthClient({
    baseURL: "http://auth.test",
    fetchOptions: { customFetchImpl: fetchImpl },
  });

  return { client, fetchImpl };
};

/**
 * The ways a server-rendered page load turns out to be anonymous.
 *
 * The interesting one is the middle: better-auth answers 200 with an empty body
 * for a cookie it no longer recognises, so status alone is not the test.
 */
describe("resolveSession", () => {
  it("does not call the auth server without a cookie", async () => {
    const { client, fetchImpl } = clientResponding({ body: { user } });

    expect(await resolveSession(undefined, client)).toBeNull();
    expect(await resolveSession("", client)).toBeNull();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("forwards the cookie it was given", async () => {
    const { client, fetchImpl } = clientResponding({ body: { user } });

    await resolveSession("better-auth.session_token=abc", client);

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toContain("/api/auth/get-session");
    expect(new Headers(init.headers).get("cookie")).toBe("better-auth.session_token=abc");
  });

  it("returns the user for a live session", async () => {
    const { client } = clientResponding({ body: { user } });

    expect(await resolveSession("session=live", client)).toMatchObject({ email: user.email });
  });

  it("treats an empty 200 as signed out, which is what a stale cookie gets", async () => {
    const { client } = clientResponding({});

    expect(await resolveSession("session=stale", client)).toBeNull();
  });

  it("treats a rejected request as signed out rather than throwing", async () => {
    const { client } = clientResponding({ status: 401, body: { message: "nope" } });

    expect(await resolveSession("session=bad", client)).toBeNull();
  });
});
