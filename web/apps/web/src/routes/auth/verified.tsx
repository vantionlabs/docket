import { sessionAtom } from "@/atom/session-atoms.js";
import { AuthCard, AuthLink } from "@/components/auth/auth-card.js";
import { Button } from "@/components/ui/button.js";
import { useAtomRefresh } from "@effect/atom-react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import * as React from "react";

/**
 * Where better-auth's verify endpoint lands after following the emailed link.
 *
 * It appends `?error=` when the token was invalid or expired; on success the
 * session cookie is already set, so the identity only needs re-reading.
 */
const Verified = () => {
  const { error } = Route.useSearch();
  const refresh = useAtomRefresh(sessionAtom);
  const navigate = useNavigate();

  React.useEffect(() => {
    if (error === undefined) refresh();
  }, [error, refresh]);

  if (error !== undefined) {
    return (
      <AuthCard
        title="That link did not work"
        description="Verification links expire, and can only be used once."
        footer={<AuthLink to="/auth/sign-in">Back to sign in</AuthLink>}
      >
        <span />
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Email verified" description="Your address is confirmed and you are signed in.">
      <Button
        type="button"
        className="w-full"
        onClick={() =>
          void navigate({ to: "/" })}
      >
        Continue
      </Button>
    </AuthCard>
  );
};

export const Route = createFileRoute("/auth/verified")({
  validateSearch: (search: Record<string, unknown>) => ({
    error: typeof search["error"] === "string" ? search["error"] : undefined,
  }),
  component: Verified,
});
