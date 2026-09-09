import { resendVerificationEmail } from "@/atom/session-atoms.js";
import { Alert, AlertDescription } from "@/components/ui/alert.js";
import { Button } from "@/components/ui/button.js";
import { Effect } from "effect";
import * as React from "react";

/**
 * Shown while an account is unverified.
 *
 * Sign-in is deliberately not blocked — flip `requireEmailVerification` in
 * `apps/server/src/iam/Options.ts` if you want that instead. Gating here
 * would strand anyone whose verification email failed to send.
 */
export const VerifyEmailBanner = (props: { readonly email: string; }) => {
  const [state, setState] = React.useState<"idle" | "sending" | "sent" | "failed">("idle");

  const resend = () => {
    setState("sending");

    void Effect.runPromise(Effect.result(resendVerificationEmail(props.email))).then((result) =>
      setState(result._tag === "Success" ? "sent" : "failed")
    );
  };

  return (
    <Alert>
      <AlertDescription className="flex items-center justify-between gap-4">
        <span>
          {state === "sent"
            ? "Verification email sent. Check your inbox."
            : state === "failed"
            ? "We could not send that email. Try again shortly."
            : "Your email address is not verified yet."}
        </span>
        {state !== "sent" && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={state === "sending"}
            onClick={resend}
          >
            Resend
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
};
