import type { LinkProps } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { Building2, KeyRound, ScrollText, ShieldCheck, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * Exported so the command palette can offer the same destinations. Two lists
 * would mean a settings page that exists in the sidebar and not in ⌘K.
 */
export const settingsGroups: ReadonlyArray<{
  readonly label: string;
  readonly items: ReadonlyArray<{
    readonly to: NonNullable<LinkProps["to"]>;
    readonly label: string;
    readonly icon: LucideIcon;
  }>;
}> = [
  {
    label: "Organization",
    items: [
      { to: "/settings/general", label: "General", icon: Building2 },
      { to: "/settings/members", label: "Members", icon: Users },
      { to: "/settings/roles", label: "Roles", icon: ShieldCheck },
    ],
  },
  {
    label: "Developer",
    items: [
      { to: "/settings/api-keys", label: "API keys", icon: KeyRound },
    ],
  },
  {
    label: "Governance",
    items: [
      { to: "/settings/audit", label: "Audit log", icon: ScrollText },
    ],
  },
];

const item =
  "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground";
const active = "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs bg-accent text-foreground";

/**
 * A second, narrower sidebar inside the settings pane.
 *
 * Grouped and deliberately quieter than the app's own navigation — smaller type,
 * no accent — so that two vertical navs side by side still read as a hierarchy
 * rather than as competing menus.
 */
export const SettingsNav = () => (
  <nav className="flex w-44 shrink-0 flex-col gap-4">
    {settingsGroups.map((group) => (
      <div key={group.label} className="flex flex-col gap-1">
        <p className="px-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
          {group.label}
        </p>
        {group.items.map(({ to, label, icon: Icon }) => (
          <Link key={to} to={to} className={item} activeProps={{ className: active }}>
            <Icon className="size-3.5" aria-hidden />
            {label}
          </Link>
        ))}
      </div>
    ))}
  </nav>
);
