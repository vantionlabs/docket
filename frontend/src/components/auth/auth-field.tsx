"use client";

import type { AnyFieldApi } from "@tanstack/react-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** A labelled input bound to a TanStack Form field, with inline validation. */
export function AuthField({
  field,
  label,
  type = "text",
}: {
  field: AnyFieldApi;
  label: string;
  type?: string;
}) {
  const error = field.state.meta.isTouched ? field.state.meta.errors[0] : undefined;
  const message = typeof error === "string" ? error : error?.message;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={field.name}>{label}</Label>
      <Input
        id={field.name}
        name={field.name}
        type={type}
        value={field.state.value}
        aria-invalid={!!message}
        onBlur={field.handleBlur}
        onChange={(e) => field.handleChange(e.target.value)}
      />
      {message && <span className="text-destructive text-xs">{message}</span>}
    </div>
  );
}
