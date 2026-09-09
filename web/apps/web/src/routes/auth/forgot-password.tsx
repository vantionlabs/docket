import { requestPasswordReset } from "@/atom/session-atoms.js";
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
    onSubmit: (_, { decoded }) => requestPasswordReset(decoded.email),
  },
);

const ForgotPassword = () => {
  const submit = useAtomSet(form.submit);
  const result = useAtomValue(form.submit);
  // Reveal errors from the first submit attempt, not just failed ones.
  const submitted = useAtomValue(form.submitCount) > 0;

  return (
    <AuthCard
      title="Reset your password"
      description="We'll email you a link to choose a new one."
      footer={<AuthLink to="/auth/sign-in">Back to sign in</AuthLink>}
    >
      <form.Initialize defaultValues={{ email: "" }}>
        <div className="flex flex-col gap-4">
          <form.email submitted={submitted} />
          {
            /* Deliberately identical whether or not the address exists — a
              different message here would be an account-enumeration oracle. */
          }
          {result._tag === "Success" && (
            <Alert>
              <AlertDescription>
                If that address has an account, a reset link is on its way.
              </AlertDescription>
            </Alert>
          )}
          {result._tag === "Failure" && (
            <Alert variant="destructive">
              <AlertDescription>
                {submitMessage(result, "We could not send that email. Try again shortly.")}
              </AlertDescription>
            </Alert>
          )}
          <Button
            type="button"
            className="w-full"
            disabled={result.waiting}
            onClick={() => submit()}
          >
            Send reset link
          </Button>
        </div>
      </form.Initialize>
    </AuthCard>
  );
};

export const Route = createFileRoute("/auth/forgot-password")({ component: ForgotPassword });
