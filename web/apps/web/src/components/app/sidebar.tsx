import { signOut } from "@/atom/session-atoms.js";
import { OrgSwitcher } from "@/components/app/org-switcher.js";
import { Button } from "@/components/ui/button.js";
import { Separator } from "@/components/ui/separator.js";
import type { LinkProps } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { Effect } from "effect";
import { LayoutDashboard, Settings, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** Exported for the command palette, so the two cannot list different pages. */
export const nav: ReadonlyArray<{
  readonly to: NonNullable<LinkProps["to"]>;
  readonly label: string;
  readonly icon: LucideIcon;
  readonly exact?: boolean;
}> = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { to: "/contacts", label: "Contacts", icon: Users },
  // `/settings` rather than a subpage: it redirects to General, and matching
  // non-exactly is what keeps this item lit on every settings page instead of
  // only one of them.
  { to: "/settings", label: "Settings", icon: Settings },
];

const item =
  "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground";
const active = "flex items-center gap-2 rounded-md px-3 py-2 text-sm bg-accent text-foreground";

/** Real links throughout, so middle-click and copy-link behave as expected. */
export const Sidebar = (props: { readonly email: string; readonly onSignOut: () => void; }) => (
  <aside className="flex w-56 shrink-0 flex-col justify-between border-r border-border p-4">
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        <div>
          <p className="text-sm font-semibold">forge</p>
          <p className="text-muted-foreground text-xs">workspace</p>
        </div>
        <OrgSwitcher />
      </div>

      {/* One line, and the difference between a feature and a secret. */}
      <p className="text-muted-foreground flex items-center gap-1.5 px-1 text-xs">
        Search
        <kbd className="rounded border border-border bg-muted px-1 py-0.5 font-mono text-[10px]">
          ⌘K
        </kbd>
      </p>

      <Separator />

      <nav className="flex flex-col gap-1">
        {nav.map(({ to, label, icon: Icon, exact }) => (
          <Link
            key={to}
            to={to}
            className={item}
            {...(exact === true ? { activeOptions: { exact: true } } : {})}
            activeProps={{ className: active }}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        ))}
      </nav>
    </div>

    <div className="flex flex-col gap-2">
      <p className="truncate font-mono text-xs text-muted-foreground">{props.email}</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => void Effect.runPromise(signOut).then(props.onSignOut)}
      >
        Sign out
      </Button>
    </div>
  </aside>
);
