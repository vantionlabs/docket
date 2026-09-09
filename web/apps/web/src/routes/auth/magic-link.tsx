import { sendMagicLink } from "@/atom/session-atoms.js";
import { AuthCard, AuthLink } from "@/components/auth/auth-card.js";
import { textField } from "@/components/auth/text-field.js";
import { Alert, AlertDescription } from "@/components/ui/alert.js";
import { Button } from "@/components/ui/button.js";
import { submitMessage } from "@/lib/auth/auth-result.js";
import { Email } from "@/lib/auth/schemas.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import { FormBuilder, FormReact } from "@lucas-barake/effect-form-react";
import { createFileRoute } from "@tanstack/react-router";

const form = FormReact.make(
  FormBuilder.empty.addField("email", Email),
  {
    mode: { validation: "onBlur" },
    fields: { email: textField({ label: "Email", type: "email", autoComplete: "email" }) },
    onSubmit: (_, { decoded }) => sendMagicLink(decoded.email),
  },
);

const MagicLink = () => {
  const submit = useAtomSet(form.submit);
  const result = useAtomValue(form.submit);
  // Reveal errors from the first submit attempt, not just failed ones.
  const submitted = useAtomValue(form.submitCount) > 0;

  return (
    <AuthCard
      title="Sign in with a link"
      description="No password needed — we'll email you a one-time link."
      footer={
        <div className="flex flex-col gap-1">
          <AuthLink to="/auth/otp">Use a code instead</AuthLink>
          <AuthLink to="/auth/sign-in">Back to sign in</AuthLink>
        </div>
      }
    >
      <form.Initialize defaultValues={{ email: "" }}>
        <div className="flex flex-col gap-4">
          <form.email submitted={submitted} />
          {
            /* Same response either way, so this cannot be used to probe which
              addresses have accounts. */
          }
          {result._tag === "Success" && (
            <Alert>
              <AlertDescription>
                If that address has an account, a sign-in link is on its way. The link expires
                shortly and can be used once.
              </AlertDescription>
            </Alert>
          )}
          {result._tag === "Failure" && (
            <Alert variant="destructive">
              <AlertDescription>
                {submitMessage(result, "We could not send that link. Try again shortly.")}
              </AlertDescription>
            </Alert>
          )}
          <Button
            type="button"
            className="w-full"
            disabled={result.waiting}
            onClick={() => submit()}
          >
            Email me a link
          </Button>
        </div>
      </form.Initialize>
    </AuthCard>
  );
};

export const Route = createFileRoute("/auth/magic-link")({ component: MagicLink });
