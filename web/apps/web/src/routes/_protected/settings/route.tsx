import { SettingsNav } from "@/components/settings/settings-nav.js";
import { Separator } from "@/components/ui/separator.js";
import { createFileRoute, Outlet } from "@tanstack/react-router";

/** App shell owns viewport height; the settings pane owns its own scrolling. */
export const Route = createFileRoute("/_protected/settings")({
  staticData: { crumb: "Settings" },
  component: () => (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">Settings</h1>
        <p className="text-muted-foreground text-sm">
          Organization and governance
        </p>
      </div>
      <Separator />
      <div className="flex gap-8">
        <SettingsNav />
        <div className="min-w-0 max-w-3xl flex-1">
          <Outlet />
        </div>
      </div>
    </div>
  ),
});
