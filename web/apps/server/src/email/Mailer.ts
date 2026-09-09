import { Config, Context, Effect, Layer, Option, Redacted, Schema } from "effect";
import { Resend } from "resend";
import type { RenderedEmail } from "./Templates.js";

/**
 * The only send failures a caller can do anything about.
 *
 * Everything else Resend reports — a missing or restricted API key, an
 * unverified `from` address, an internal server error — is a misconfiguration
 * or an outage, so it becomes a defect rather than a typed error.
 */
export class EmailSendFailed extends Schema.TaggedError<EmailSendFailed>()("EmailSendFailed", {
  reason: Schema.Literals(["RateLimited", "InvalidRecipient", "Unavailable"]),
}) {}

export interface EmailMessage extends RenderedEmail {
  readonly to: string;
}

export interface MailerService {
  readonly send: (message: EmailMessage) => Effect.Effect<void, EmailSendFailed>;
}

/** `undefined` means "not actionable" — the caller cannot fix it, so it dies. */
const actionableReason = (code: string): EmailSendFailed["reason"] | undefined => {
  switch (code) {
    case "rate_limit_exceeded":
    case "daily_quota_exceeded":
    case "monthly_quota_exceeded":
      return "RateLimited";
    case "validation_error":
    case "invalid_parameter":
    case "missing_required_field":
      return "InvalidRecipient";
    default:
      return undefined;
  }
};

export class Mailer extends Context.Service<Mailer, MailerService>()("Mailer") {
  /**
   * Without a key, mail is written to the log instead of sent.
   *
   * This is what makes a fresh clone usable: signing up sends a verification
   * mail and a magic link is the whole of that sign-in flow, so a Mailer that
   * refused to start without a Resend account would make an unconfigured
   * checkout unable to authenticate anyone. The rendered text carries the link,
   * so the log is enough to follow it.
   *
   * It is a development affordance and says so, loudly, once per send.
   */
  static layerLogging: Layer.Layer<Mailer> = Layer.succeed(Mailer)({
    // The rendered text is the log message rather than an annotation, so the
    // link is readable in a terminal and does not depend on how a log handler
    // chooses to render structured fields.
    send: Effect.fn("Mailer.send")(function*(message: EmailMessage) {
      yield* Effect.logWarning(
        `RESEND_API_KEY is unset — not sending.\n\n${message.text}`,
      ).pipe(Effect.annotateLogs({ to: message.to, subject: message.subject }));
    }),
  });

  static layerResend: Layer.Layer<Mailer> = Layer.effect(Mailer)(
    Effect.gen(function*() {
      const apiKey = yield* Config.redacted("RESEND_API_KEY");
      const from = yield* Config.nonEmptyString("EMAIL_FROM");
      const resend = new Resend(Redacted.value(apiKey));

      const send = Effect.fn("Mailer.send")(function*(message: EmailMessage) {
        // Resend resolves with `{ error }` rather than rejecting, so a
        // `tryPromise` catch alone would silently drop every API-level failure.
        const result = yield* Effect.tryPromise({
          try: () =>
            resend.emails.send({
              from,
              to: message.to,
              subject: message.subject,
              html: message.html,
              text: message.text,
            }),
          catch: () => new EmailSendFailed({ reason: "Unavailable" }),
        });

        if (result.error !== null) {
          const reason = actionableReason(result.error.name);

          return yield* reason === undefined
            ? Effect.die(result.error)
            : new EmailSendFailed({ reason });
        }
      });

      return { send };
    }),
  ).pipe(Layer.orDie);

  /**
   * Resend when a key is configured, the log when it is not.
   *
   * The choice is made from the environment rather than from `NODE_ENV`, so a
   * deployment that forgets the key degrades to a visible warning on every send
   * rather than failing to boot with nothing to show for it.
   */
  static layer: Layer.Layer<Mailer> = Layer.unwrap(
    Effect.gen(function*() {
      /**
       * Read as a plain string and test it here, rather than as a
       * `nonEmptyString` under `Config.option`. That combination reports an
       * empty value as a *failure* rather than as absence, and empty is exactly
       * what `.env.example` ships and what an unset platform variable becomes.
       */
      const configured = yield* Config.option(Config.string("RESEND_API_KEY"));

      return Option.isSome(configured) && configured.value.trim() !== ""
        ? Mailer.layerResend
        : Mailer.layerLogging;
    }).pipe(Effect.orDie),
  );
}
