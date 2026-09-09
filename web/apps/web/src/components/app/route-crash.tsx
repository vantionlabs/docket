import { Button } from "@/components/ui/button.js";
import { RotateCw, TriangleAlert } from "lucide-react";

/**
 * What a page shows when its own code throws.
 *
 * Without this, TanStack's default catch boundary renders the raw error into an
 * otherwise blank pane, which reads as the application being broken with no way
 * forward. In practice the commonest cause in development is a stale module
 * graph after a failed hot update — a full reload fixes it, and that is precisely
 * what somebody staring at the blank pane does not know.
 *
 * The message is deliberately not an apology and not a stack trace: it says what
 * to try, and leaves the detail in the console where it is actually readable.
 */
export const RouteCrash = (props: { readonly error: Error; }) => (
  <div className="flex flex-col items-start gap-4 p-8">
    <div className="flex items-start gap-3">
      <TriangleAlert className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium">This page did not load.</p>
        <p className="text-muted-foreground text-sm">
          Reloading usually fixes it. The full error is in the browser console.
        </p>
      </div>
    </div>

    <p className="text-muted-foreground max-w-lg font-mono text-xs break-words">
      {props.error.message}
    </p>

    <Button
      variant="outline"
      onClick={() => {
        // A real reload rather than a router retry: the failure this exists for
        // is a module that never finished loading, which retrying cannot mend.
        globalThis.location.reload();
      }}
    >
      <RotateCw className="size-4" aria-hidden />
      Reload
    </Button>
  </div>
);
