import { authClient } from "@/iam/auth-client.js";
import { createServerFn } from "@tanstack/react-start";
import { getRequestHeader } from "@tanstack/react-start/server";

/**
 * Who the caller is, resolved on the server before the page renders.
 *
 * The session comes from the Effect server, which owns the better-auth
 * *instance*. This does not stand up a second one: that would need the same
 * five secrets and its own PgPool, and — the reason that settles it — would be
 * a second door without `AuthHttp`'s rate limiter on it. Throttling is the
 * security boundary for a six-digit OTP.
 *
 * The cost is one internal request per server-rendered page, to a service this
 * one cannot serve a page without anyway.
 */

export type SessionUser = NonNullable<
  Awaited<ReturnType<typeof authClient.getSession>>["data"]
>["user"];

/**
 * The cookie has to be passed explicitly.
 *
 * In the browser the client picks one up ambiently; on the server there is no
 * ambient anything, only the request being handled — so forwarding it is the
 * whole job.
 *
 * Returns `null` rather than throwing for an absent or rejected session: "not
 * signed in" is an ordinary answer, and the redirect is the caller's decision.
 * The client reports a rejection in `error` rather than by throwing, so an
 * absent `data` is the whole test.
 */
export const resolveSession = async (
  cookie: string | undefined,
  client: Pick<typeof authClient, "getSession"> = authClient,
): Promise<SessionUser | null> => {
  // No cookie, no round trip. An anonymous first paint is the common case.
  if (cookie === undefined || cookie === "") return null;

  const { data } = await client.getSession({ fetchOptions: { headers: { cookie } } });

  return data?.user ?? null;
};

export const getSession = createServerFn({ method: "GET" }).handler(
  (): Promise<SessionUser | null> => resolveSession(getRequestHeader("cookie")),
);
