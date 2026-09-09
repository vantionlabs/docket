import { Input } from "@/components/ui/input.js";
import { Label } from "@/components/ui/label.js";
import { Option } from "effect";
import * as React from "react";

/**
 * Renders one effect-form field.
 *
 * Errors stay hidden until the user has actually typed something — blurring a
 * field they never filled in should not accuse them of anything. `submitted`
 * overrides that once a submit has been attempted, so pressing the button on an
 * empty form marks what is missing instead of pointing at nothing.
 */
export const textField = (options: {
  readonly label: string;
  readonly type?: "text" | "email" | "password";
  readonly autoComplete?: string;
}) =>
(props: {
  readonly field: {
    readonly value: string;
    readonly onChange: (value: string) => void;
    readonly onBlur: () => void;
    readonly error: Option.Option<string>;
    readonly isDirty: boolean;
  };
  readonly props: { readonly submitted?: boolean; };
}) => {
  const id = React.useId();
  const reveal = props.field.isDirty || props.props.submitted === true;
  const error = reveal ? props.field.error : Option.none();

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{options.label}</Label>
      <Input
        id={id}
        type={options.type ?? "text"}
        autoComplete={options.autoComplete}
        value={props.field.value}
        onChange={(event) => props.field.onChange(event.target.value)}
        onBlur={props.field.onBlur}
        aria-invalid={Option.isSome(error)}
      />
      {Option.isSome(error) && <p className="text-destructive text-xs">{error.value}</p>}
    </div>
  );
};
