import { Button } from "@/components/ui/button.js";
import { Input } from "@/components/ui/input.js";
import { Label } from "@/components/ui/label.js";
import * as React from "react";

export const ContactForm = (props: {
  readonly onCreate: (input: { readonly email: string; readonly fullName: string; }) => void;
  readonly pending: boolean;
}) => {
  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");

  const submit = () => {
    props.onCreate({ email: email.trim(), fullName: fullName.trim() });
    setFullName("");
    setEmail("");
  };

  return (
    <div className="flex flex-wrap items-end gap-2 rounded-md border border-border p-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="contact-name">Name</Label>
        <Input
          id="contact-name"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="contact-email">Email</Label>
        <Input
          id="contact-email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>
      <Button
        type="button"
        disabled={props.pending || fullName.trim() === "" || email.trim() === ""}
        onClick={submit}
      >
        Add contact
      </Button>
    </div>
  );
};
