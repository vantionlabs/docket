/**
 * Transactional email bodies as pure functions.
 *
 * Deliberately plain strings rather than React — nothing in the server package
 * should need a renderer. Swap in `@react-email/components` here if templates
 * outgrow this.
 */
export interface RenderedEmail {
  readonly subject: string;
  readonly html: string;
  readonly text: string;
}

const layout = (heading: string, body: string) =>
  `<!doctype html><html><body style="font-family:system-ui,sans-serif;line-height:1.5">`
  + `<h1 style="font-size:18px">${heading}</h1>${body}</body></html>`;

export const magicLink = (url: string): RenderedEmail => ({
  subject: "Your sign-in link",
  html: layout(
    "Sign in",
    `<p><a href="${url}">Sign in to forge</a></p><p>This link expires shortly and can be used once.</p>`,
  ),
  text: `Sign in to forge: ${url}\n\nThis link expires shortly and can be used once.`,
});

export const emailOtp = (code: string): RenderedEmail => ({
  subject: `${code} is your forge code`,
  html: layout(
    "Your sign-in code",
    `<p style="font-size:24px;letter-spacing:4px"><strong>${code}</strong></p>`,
  ),
  text: `Your forge sign-in code is ${code}.`,
});

export const resetPassword = (url: string): RenderedEmail => ({
  subject: "Reset your password",
  html: layout(
    "Reset your password",
    `<p><a href="${url}">Choose a new password</a></p><p>If you did not request this, ignore this email.</p>`,
  ),
  text: `Reset your forge password: ${url}\n\nIf you did not request this, ignore this email.`,
});

export const verifyEmail = (url: string): RenderedEmail => ({
  subject: "Verify your email",
  html: layout("Verify your email", `<p><a href="${url}">Confirm this address</a></p>`),
  text: `Confirm your forge email address: ${url}`,
});
