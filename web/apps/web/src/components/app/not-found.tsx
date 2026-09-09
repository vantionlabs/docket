import { Button } from "@/components/ui/button.js";
import { Link } from "@tanstack/react-router";
import { FileQuestion } from "lucide-react";

/**
 * A path that matched no route.
 *
 * Declared on the root so it covers every miss, including the ones nothing
 * routed at all — without it TanStack renders a bare "Not Found" and warns about
 * it on every request, favicons included.
 */
export const NotFound = () => (
  <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
    <FileQuestion className="size-6 text-muted-foreground" aria-hidden />
    <div className="flex flex-col gap-1">
      <p className="text-sm font-medium">That page does not exist.</p>
      <p className="text-muted-foreground text-sm">
        The link may be out of date, or the address mistyped.
      </p>
    </div>
    <Button variant="outline" render={<Link to="/" />}>Back to the dashboard</Button>
  </div>
);
