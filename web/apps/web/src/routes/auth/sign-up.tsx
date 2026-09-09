import { sessionAtom, signInWithGoogle, signUp } from "@/atom/session-atoms.js";
import { AuthCard, AuthLink, GoogleButton } from "@/components/auth/auth-card.js";
import { textField } from "@/components/auth/text-field.js";
import { Alert, AlertDescription } from "@/components/ui/alert.js";
import { Button } from "@/components/ui/button.js";
import { submitMessage } from "@/lib/auth/auth-result.js";
import { Email, NewPassword } from "@/lib/auth/schemas.js";
import { useAtomRefresh, useAtomSet, useAtomValue } from "@effect/atom-react";
import { FormBuilder, FormReact } from "@lucas-barake/effect-form-react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Effect } from "effect";
import { AsyncResult } from "effect/unstable/reactivity";
import * as React from "react";

const form = FormReact.make(
  FormBuilder.empty
    .addField("email", Email)
    // The minimum is enforced here rather than only server-side, so the rule is
    // visible before a round trip.
    .addField("password", NewPassword),
  {
    mode: { validation: "onBlur" },
    fields: {
      email: textField({ label: "Email", type: "email", autoComplete: "email" }),
      password: textField({ label: "Password", type: "password", autoComplete: "new-password" }),
    },
    onSubmit: (_, { decoded }) => signUp(decoded),
  },
);

const SignUp = () => {
  const submit = useAtomSet(form.submit);
  const result = useAtomValue(form.submit);
  // Reveal errors from the first submit attempt, not just failed ones.
  const submitted = useAtomValue(form.submitCount) > 0;
  const refresh = useAtomRefresh(sessionAtom);
  /**
   * A selector, not the session itself. This page only needs to know *whether* a
   * session resolved, so subscribing to the whole thing would re-render it every
   * time any field of the identity changed — permissions, active organization —
   * none of which it reads.
   */
  const signedIn = useAtomValue(sessionAtom, AsyncResult.isSuccess);
  const navigate = useNavigate();

  /**
   * Two steps on purpose. The credentials landing is not the same event as the
   * session being readable, and navigating on the first one races the second.
   */
  React.useEffect(() => {
    if (result._tag === "Success") refresh();
  }, [result, refresh]);

  React.useEffect(() => {
    if (result._tag === "Success" && signedIn) {
      void navigate({ to: "/" });
    }
  }, [result, signedIn, navigate]);

  return (
    <AuthCard
      title="Create an account"
      description="A personal organization is created with your account."
      footer={
        <span>
          Already have an account? <AuthLink to="/auth/sign-in">Sign in</AuthLink>
        </span>
      }
    >
      <form.Initialize defaultValues={{ email: "", password: "" }}>
        <div className="flex flex-col gap-4">
          <form.email submitted={submitted} />
          <form.password submitted={submitted} />
          {result._tag === "Failure" && (
            <Alert variant="destructive">
              <AlertDescription>
                {submitMessage(result, "Could not create that account. It may already exist.")}
              </AlertDescription>
            </Alert>
          )}
          <Button
            type="button"
            className="w-full"
            disabled={result.waiting}
            onClick={() => submit()}
          >
            Create account
          </Button>
        </div>
      </form.Initialize>
      <GoogleButton onClick={() => void Effect.runPromise(signInWithGoogle)} />
    </AuthCard>
  );
};

export const Route = createFileRoute("/auth/sign-up")({ component: SignUp });
