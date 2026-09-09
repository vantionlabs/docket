import { describe, expect, it } from "@effect/vitest";
import { Mailer } from "@forge/server/email/Mailer";
import { ConfigProvider, Effect, Logger } from "effect";

const withEnv = (env: Record<string, string>) =>
  Effect.provideService(
    ConfigProvider.ConfigProvider,
    ConfigProvider.fromEnvRecord(env, { preserveEmptyStrings: true }),
  );

const sendOne = Effect.gen(function*() {
  const mailer = yield* Mailer;

  yield* mailer.send({
    to: "reader@example.com",
    subject: "Your sign-in link",
    html: "<p>link</p>",
    text: "Sign in: https://example.com/verify?token=abc",
  });
});

/** Collects what a send would have written, in place of the console. */
const captureInto = (lines: Array<string>) =>
  Logger.layer([Logger.make(({ message }) => lines.push(String(message)))]);

describe("Mailer", () => {
  /**
   * A fresh clone has no Resend account, and every way into the application
   * goes through an email — so a Mailer that refused to build without a key
   * would leave it unable to authenticate anyone.
   */
  it.effect("without a key, logs the mail instead of sending it", () =>
    Effect.gen(function*() {
      const lines: Array<string> = [];

      yield* sendOne.pipe(
        Effect.provide(Mailer.layer),
        Effect.provide(captureInto(lines)),
        withEnv({ EMAIL_FROM: "forge@example.com" }),
      );

      const written = lines.join("\n");

      expect(written).toContain("RESEND_API_KEY is unset");
      // The whole point: the link is followable from the log.
      expect(written).toContain("https://example.com/verify?token=abc");
    }));

  /**
   * `.env.example` ships the key as an empty string, which is what a first
   * `cp` leaves behind.
   */
  it.effect("treats an empty key the same as an unset one", () =>
    Effect.gen(function*() {
      const lines: Array<string> = [];

      yield* sendOne.pipe(
        Effect.provide(Mailer.layer),
        Effect.provide(captureInto(lines)),
        withEnv({ EMAIL_FROM: "forge@example.com", RESEND_API_KEY: "" }),
      );

      expect(lines.join("\n")).toContain("RESEND_API_KEY is unset");
    }));
});
