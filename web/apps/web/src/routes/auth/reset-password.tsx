import { resetPassword } from "@/atom/session-atoms.js";
import { AuthCard, AuthLink } from "@/components/auth/auth-card.js";
import { textField } from "@/components/auth/text-field.js";
import { Alert, AlertDescription } from "@/components/ui/alert.js";
import { Button } from "@/components/ui/button.js";
import { NewPassword } from "@/lib/auth/schemas.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import { FormBuilder, FormReact } from "@lucas-barake/effect-form-react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import * as React from "react";

const form = FormReact.make(
  FormBuilder.empty.addField("newPassword", NewPassword),
  {
    mode: { validation: "onBlur" },
    fields: {
      newPassword: textField({
        label: "New password",
        type: "password",
        autoComplete: "new-password",
      }),
    },
    onSubmit: (token: string, { decoded }) =>
      resetPassword({ token, newPassword: decoded.newPassword }),
  },
);

const ResetPassword = () => {
  const { token } = Route.useSearch();
  const submit = useAtomSet(form.submit);
  const result = useAtomValue(form.submit);
  // Reveal errors from the first submit attempt, not just failed ones.
  const submitted = useAtomValue(form.submitCount) > 0;
  const navigate = useNavigate();

  React.useEffect(() => {
    if (result._tag === "Success") void navigate({ to: "/auth/sign-in" });
  }, [result, navigate]);

  if (token === undefined) {
    return (
      <AuthCard
        title="Reset link invalid"
        description="This link is missing its token, or has already been used."
        footer={<AuthLink to="/auth/forgot-password">Request a new link</AuthLink>}
      >
        <span />
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Choose a new password"
      description="Your other sessions stay signed in until they expire."
      footer={<AuthLink to="/auth/sign-in">Back to sign in</AuthLink>}
    >
      <form.Initialize defaultValues={{ newPassword: "" }}>
        <div className="flex flex-col gap-4">
          <form.newPassword submitted={submitted} />
          {result._tag === "Failure" && (
            <Alert variant="destructive">
              <AlertDescription>
                That link has expired or has already been used.
              </AlertDescription>
            </Alert>
          )}
          <Button
            type="button"
            className="w-full"
            disabled={result.waiting}
            onClick={() => submit(token)}
          >
            Set new password
          </Button>
        </div>
      </form.Initialize>
    </AuthCard>
  );
};

export const Route = createFileRoute("/auth/reset-password")({
  // better-auth appends `?token=` to the emailed link.
  validateSearch: (search: Record<string, unknown>) => ({
    token: typeof search["token"] === "string" ? search["token"] : undefined,
  }),
  component: ResetPassword,
});
