import { AppRpc } from "@/atom/app-rpc.js";
import { Keys } from "@/atom/reactivity-keys.js";
import { authClient } from "@/iam/auth-client.js";
import { Effect, Schema } from "effect";
import { Atom } from "effect/unstable/reactivity";

/**
 * Sign-in failures a form can act on. Anything else — a 500, a broken proxy —
 * stays a defect rather than becoming a message the user cannot use.
 */
export class SignInFailed extends Schema.TaggedError<SignInFailed>()("SignInFailed", {
  reason: Schema.Literals(["InvalidCredentials", "RateLimited"]),
}) {}

/**
 * The signed-in identity, or a failure when there is no session.
 *
 * The identity carries the active organization, its role and the permissions
 * that follow from it, so it subscribes to the `organization` key and re-reads
 * itself whenever the active organization changes. Signing in and out happen
 * outside any atom, and still refresh it with `useAtomRefresh`.
 */
export const sessionAtom = Atom.withReactivity([Keys.organization])(
  AppRpc.runtime.atom(
    Effect.gen(function*() {
      const client = yield* AppRpc;

      return yield* client("Me", undefined);
    }),
  ),
);

/**
 * better-auth's client resolves with `{ error }` rather than rejecting, so the
 * result is inspected instead of being caught.
 */
const fromAuthResult = (result: { readonly error: { readonly status?: number; } | null; }) =>
  result.error === null
    ? Effect.void
    : new SignInFailed({
      reason: result.error.status === 429 ? "RateLimited" : "InvalidCredentials",
    });

export const signIn = (credentials: { readonly email: string; readonly password: string; }) =>
  Effect.promise(() => authClient.signIn.email(credentials)).pipe(Effect.flatMap(fromAuthResult));

export const signUp = (credentials: { readonly email: string; readonly password: string; }) =>
  Effect.promise(() =>
    authClient.signUp.email({
      ...credentials,
      name: credentials.email.split("@")[0] ?? "You",
    })
  ).pipe(Effect.flatMap(fromAuthResult));

export const signOut = Effect.promise(() => authClient.signOut());

/** Sends the reset link. `redirectTo` is where the emailed link lands. */
export const requestPasswordReset = (email: string) =>
  Effect.promise(() =>
    authClient.requestPasswordReset({
      email,
      redirectTo: `${window.location.origin}/auth/reset-password`,
    })
  ).pipe(Effect.flatMap(fromAuthResult));

export const resetPassword = (options: { readonly token: string; readonly newPassword: string; }) =>
  Effect.promise(() => authClient.resetPassword(options)).pipe(Effect.flatMap(fromAuthResult));

/**
 * Emails a one-time sign-in link. The link lands on better-auth's own verify
 * endpoint, which sets the session cookie and redirects to `callbackURL` — so
 * there is no client route to handle it.
 */
export const sendMagicLink = (email: string) =>
  Effect.promise(() => authClient.signIn.magicLink({ email, callbackURL: window.location.origin }))
    .pipe(Effect.flatMap(fromAuthResult));

/** Emails a six digit code. `sign-in` also creates the user if none exists. */
export const sendOtp = (email: string) =>
  Effect.promise(() => authClient.emailOtp.sendVerificationOtp({ email, type: "sign-in" })).pipe(
    Effect.flatMap(fromAuthResult),
  );

export const verifyOtp = (options: { readonly email: string; readonly otp: string; }) =>
  Effect.promise(() => authClient.signIn.emailOtp(options)).pipe(Effect.flatMap(fromAuthResult));

/**
 * Re-sends the verification email. `callbackURL` is where better-auth's own
 * verify endpoint redirects once the link is followed.
 */
export const resendVerificationEmail = (email: string) =>
  Effect.promise(() =>
    authClient.sendVerificationEmail({
      email,
      callbackURL: `${window.location.origin}/auth/verified`,
    })
  ).pipe(Effect.flatMap(fromAuthResult));

/**
 * Full-page redirect to Google. Nothing resumes after this call, so there is no
 * result to inspect.
 */
export const signInWithGoogle = Effect.promise(() =>
  authClient.signIn.social({ provider: "google", callbackURL: window.location.origin })
);
