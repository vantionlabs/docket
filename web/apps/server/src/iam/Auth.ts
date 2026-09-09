import { PgPool } from "@forge/database/PgPool";
import { Config, Context, Effect, Layer, Option, Redacted } from "effect";
import type { EmailMessage } from "../email/Mailer.js";
import { Mailer } from "../email/Mailer.js";
import type { AuthInstance } from "./Options.js";
import { makeAuth } from "./Options.js";

/**
 * better-auth, behind the only seam in the codebase that leaves the Effect
 * runtime.
 *
 * better-auth invokes its `sendX` callbacks from its own promise chain, so an
 * Effect has to be run to completion inside them. Because `Mailer` is resolved
 * to a value here, `mailer.send` carries no remaining requirements and a bare
 * `Effect.runPromise` suffices — there is no context to thread through. A
 * rejected promise surfaces to the caller as a better-auth error, which is the
 * behaviour we want when mail cannot be sent.
 */
export class Auth extends Context.Service<Auth, AuthInstance>()("Auth") {
  static layer: Layer.Layer<Auth, never, PgPool | Mailer> = Layer.effect(Auth)(
    Effect.gen(function*() {
      const pool = yield* PgPool;
      const mailer = yield* Mailer;

      const baseURL = yield* Config.nonEmptyString("AUTH_BASE_URL").pipe(
        Config.withDefault("http://localhost:3000"),
      );
      const secret = yield* Config.redacted("AUTH_SECRET");
      const webUrl = yield* Config.nonEmptyString("WEB_URL").pipe(
        Config.withDefault("http://localhost:5173"),
      );

      /**
       * Set only when the web app and the API are on different subdomains of one
       * parent — `.example.com`. Left unset they share a host and better-auth's
       * default is correct.
       */
      const cookieDomain = yield* Config.option(Config.nonEmptyString("AUTH_COOKIE_DOMAIN"));

      const google = yield* Config.all({
        clientId: Config.nonEmptyString("GOOGLE_CLIENT_ID"),
        clientSecret: Config.nonEmptyString("GOOGLE_CLIENT_SECRET"),
      }).pipe(Config.option);

      const sendEmail = (message: EmailMessage): Promise<void> =>
        Effect.runPromise(mailer.send(message));

      return makeAuth({
        pool,
        baseURL,
        secret: Redacted.value(secret),
        trustedOrigins: [webUrl],
        cookieDomain: Option.getOrUndefined(cookieDomain),
        google: Option.getOrUndefined(google),
        sendEmail,
      });
    }),
  ).pipe(Layer.orDie);
}
