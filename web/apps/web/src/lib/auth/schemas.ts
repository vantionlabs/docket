import { Schema } from "effect";

/**
 * Field schemas for the auth forms.
 *
 * Every check carries a `message`, which the default formatter prefers over its
 * generated `Expected a value with a length of at least 8`. Declared once here
 * so the same rule cannot drift between the sign-up and reset-password pages.
 */
export const Email = Schema.String.check(
  Schema.isNonEmpty({ message: "Enter your email address." }),
  // Deliberately permissive: the only real proof an address works is that mail
  // to it arrives, and over-strict patterns reject valid addresses.
  Schema.isIncludes("@", { message: "That does not look like an email address." }),
);

export const NewPassword = Schema.String.check(
  Schema.isNonEmpty({ message: "Choose a password." }),
  Schema.isMinLength(8, { message: "Use at least 8 characters." }),
);

/** Sign-in never states the rule — that would leak how the stored password looks. */
export const CurrentPassword = Schema.String.check(
  Schema.isNonEmpty({ message: "Enter your password." }),
);

export const OtpCode = Schema.String.check(
  Schema.isNonEmpty({ message: "Enter the code we emailed you." }),
  Schema.isMinLength(6, { message: "The code is 6 digits." }),
  Schema.isMaxLength(6, { message: "The code is 6 digits." }),
);
