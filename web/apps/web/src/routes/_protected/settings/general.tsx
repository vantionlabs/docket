import {
  deleteOrganizationAtom,
  organizationsAtom,
  renameOrganizationAtom,
} from "@/atom/organization-atoms.js";
import { DangerZone } from "@/components/settings/danger-zone.js";
import { Button } from "@/components/ui/button.js";
import { Input } from "@/components/ui/input.js";
import { Label } from "@/components/ui/label.js";
import { Separator } from "@/components/ui/separator.js";
import { Skeleton } from "@/components/ui/skeleton.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import { createFileRoute } from "@tanstack/react-router";
import { Exit } from "effect";
import { AsyncResult } from "effect/unstable/reactivity";
import * as React from "react";
import { toast } from "sonner";

const General = () => {
  const organizations = useAtomValue(organizationsAtom);
  const rename = useAtomSet(renameOrganizationAtom);
  const remove = useAtomSet(deleteOrganizationAtom, { mode: "promiseExit" });
  const removing = useAtomValue(deleteOrganizationAtom);

  const active = AsyncResult.isSuccess(organizations)
    ? organizations.value.find((membership) => membership.isActive)
    : undefined;

  const [name, setName] = React.useState("");
  // The saved name wins whenever it changes underneath the field — another tab,
  // or a switch of organization.
  const [lastActive, setLastActive] = React.useState(active?.name ?? "");
  if ((active?.name ?? "") !== lastActive) {
    setLastActive(active?.name ?? "");
    setName(active?.name ?? "");
  }

  if (active === undefined) return <Skeleton className="h-64 w-full" />;

  const current = name === "" ? active.name : name;

  return (
    <section className="flex flex-col gap-8">
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="text-base font-semibold">General</h2>
          <p className="text-muted-foreground text-sm">
            Name and identifiers for this organization.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="org-name">Name</Label>
          <div className="flex items-center gap-2">
            <Input
              id="org-name"
              className="max-w-sm"
              value={current}
              onChange={(event) => setName(event.target.value)}
            />
            <Button
              disabled={current.trim() === "" || current === active.name}
              onClick={() => {
                rename(current.trim());
                toast.success("Renamed");
              }}
            >
              Save
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="org-slug">Slug</Label>
          <Input
            id="org-slug"
            className="max-w-sm font-mono"
            value={active.slug}
            readOnly
            disabled
          />
          <p className="text-muted-foreground text-xs">
            Generated when the organization was created. Changing it would break any link that
            already uses it.
          </p>
        </div>
      </div>

      <Separator />

      <DangerZone
        organizationName={active.name}
        isOnlyOrganization={AsyncResult.isSuccess(organizations)
          && organizations.value.length === 1}
        pending={removing.waiting}
        onDelete={(confirmName) => {
          void remove(confirmName).then((exit) => {
            if (Exit.isSuccess(exit)) toast.success(`Deleted ${confirmName}`);
            else toast.error("Could not delete that organization");
          });
        }}
      />
    </section>
  );
};

export const Route = createFileRoute("/_protected/settings/general")({
  staticData: { crumb: "General" },
  component: General,
});
