"use client";

import { useForm } from "@tanstack/react-form";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthField } from "@/components/auth/auth-field";
import { Button } from "@/components/ui/button";
import { login } from "@/lib/auth-client";
import { credentialsSchema } from "@/lib/schemas";

export default function SignInPage() {
  const router = useRouter();

  const mutation = useMutation({
    mutationFn: (v: { email: string; password: string }) => login(v.email, v.password),
    onSuccess: () => {
      // The cookie is set; navigate — the server layout re-checks the session.
      router.replace("/");
    },
  });

  const form = useForm({
    defaultValues: { email: "", password: "" },
    validators: { onSubmit: credentialsSchema },
    onSubmit: ({ value }) => mutation.mutateAsync(value),
  });

  return (
    <AuthCard title="Sign in" footerPrompt="No account?" footerHref="/sign-up" footerLink="Sign up">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void form.handleSubmit();
        }}
        className="flex flex-col gap-4"
      >
        <form.Field name="email">
          {(field) => <AuthField field={field} label="Email" type="email" />}
        </form.Field>
        <form.Field name="password">
          {(field) => <AuthField field={field} label="Password" type="password" />}
        </form.Field>
        {mutation.isError && (
          <p className="text-destructive text-sm">
            {mutation.error instanceof Error ? mutation.error.message : "Sign in failed"}
          </p>
        )}
        <Button type="submit" disabled={mutation.isPending} className="mt-2">
          {mutation.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthCard>
  );
}
