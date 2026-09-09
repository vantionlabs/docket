import { sendOtp, sessionAtom, verifyOtp } from "@/atom/session-atoms.js";
import { AuthCard, AuthLink } from "@/components/auth/auth-card.js";
import { textField } from "@/components/auth/text-field.js";
import { Alert, AlertDescription } from "@/components/ui/alert.js";
import { Button } from "@/components/ui/button.js";
import { submitMessage } from "@/lib/auth/auth-result.js";
import { Email, OtpCode } from "@/lib/auth/schemas.js";
import { useAtomRefresh, useAtomSet, useAtomValue } from "@effect/atom-react";
import { FormBuilder, FormReact } from "@lucas-barake/effect-form-react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import * as React from "react";

const requestForm = FormReact.make(
  FormBuilder.empty.addField("email", Email),
  {
    mode: { validation: "onBlur" },
    fields: { email: textField({ label: "Email", type: "email", autoComplete: "email" }) },
    onSubmit: (_, { decoded }) => sendOtp(decoded.email),
  },
);

const verifyForm = FormReact.make(
  // Six digits, checked here so an obviously malformed code never costs one of
  // the server's rate-limited attempts.
  FormBuilder.empty.addField("otp", OtpCode),
  {
    mode: { validation: "onBlur" },
    fields: { otp: textField({ label: "Code", autoComplete: "one-time-code" }) },
    onSubmit: (email: string, { decoded }) => verifyOtp({ email, otp: decoded.otp }),
  },
);

const RequestStep = (props: { readonly onSent: (email: string) => void; }) => {
  const submit = useAtomSet(requestForm.submit);
  const result = useAtomValue(requestForm.submit);
  const submitted = useAtomValue(requestForm.submitCount) > 0;
  const values = useAtomValue(requestForm.values);

  React.useEffect(() => {
    if (result._tag !== "Success") return;
    if (values._tag === "Some") props.onSent(values.value.email);
  }, [result, values, props]);

  return (
    <requestForm.Initialize defaultValues={{ email: "" }}>
      <div className="flex flex-col gap-4">
        <requestForm.email submitted={submitted} />
        {result._tag === "Failure" && (
          <Alert variant="destructive">
            <AlertDescription>
              {submitMessage(result, "We could not send that code. Try again shortly.")}
            </AlertDescription>
          </Alert>
        )}
        <Button type="button" className="w-full" disabled={result.waiting} onClick={() => submit()}>
          Email me a code
        </Button>
      </div>
    </requestForm.Initialize>
  );
};

const VerifyStep = (props: { readonly email: string; }) => {
  const submit = useAtomSet(verifyForm.submit);
  const result = useAtomValue(verifyForm.submit);
  const submitted = useAtomValue(verifyForm.submitCount) > 0;
  const refresh = useAtomRefresh(sessionAtom);
  const navigate = useNavigate();

  React.useEffect(() => {
    if (result._tag !== "Success") return;

    refresh();
    void navigate({ to: "/" });
  }, [result, refresh, navigate]);

  return (
    <verifyForm.Initialize defaultValues={{ otp: "" }}>
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground text-sm">
          Enter the code sent to <span className="font-mono">{props.email}</span>.
        </p>
        <verifyForm.otp submitted={submitted} />
        {result._tag === "Failure" && (
          <Alert variant="destructive">
            <AlertDescription>That code is wrong or has expired.</AlertDescription>
          </Alert>
        )}
        <Button
          type="button"
          className="w-full"
          disabled={result.waiting}
          onClick={() => submit(props.email)}
        >
          Sign in
        </Button>
      </div>
    </verifyForm.Initialize>
  );
};

const Otp = () => {
  const [sentTo, setSentTo] = React.useState<string | undefined>(undefined);

  return (
    <AuthCard
      title="Sign in with a code"
      description={sentTo === undefined
        ? "We'll email you a six digit code."
        : "Check your email for the code."}
      footer={
        <div className="flex flex-col gap-1">
          <AuthLink to="/auth/magic-link">Use a link instead</AuthLink>
          <AuthLink to="/auth/sign-in">Back to sign in</AuthLink>
        </div>
      }
    >
      {sentTo === undefined ? <RequestStep onSent={setSentTo} /> : <VerifyStep email={sentTo} />}
    </AuthCard>
  );
};

export const Route = createFileRoute("/auth/otp")({ component: Otp });
