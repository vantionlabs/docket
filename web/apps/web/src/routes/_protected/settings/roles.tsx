import { rolesAtom } from "@/atom/access-atoms.js";
import { RoleForm } from "@/components/access/role-form.js";
import { RoleTable } from "@/components/access/role-table.js";
import { QueryError } from "@/components/app/query-error.js";
import { Button } from "@/components/ui/button.js";
import { Skeleton } from "@/components/ui/skeleton.js";
import { useAtomValue } from "@effect/atom-react";
import type { CustomRole } from "@forge/domain/iam/AccessRpc";
import { createFileRoute } from "@tanstack/react-router";
import { AsyncResult } from "effect/unstable/reactivity";
import * as React from "react";

const Roles = () => {
  const roles = useAtomValue(rolesAtom);
  const [editing, setEditing] = React.useState<CustomRole | undefined>(undefined);
  const [creating, setCreating] = React.useState(false);

  if (AsyncResult.isInitial(roles)) {
    return <Skeleton className="h-48 w-full" />;
  }

  if (AsyncResult.isFailure(roles)) {
    return <QueryError result={roles} subject="roles" />;
  }

  const open = creating || editing !== undefined;
  const close = () => {
    setCreating(false);
    setEditing(undefined);
  };

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium">Custom roles</h2>
        {!open && (
          <Button type="button" size="sm" onClick={() => setCreating(true)}>New role</Button>
        )}
      </div>

      {open
        ? <RoleForm editing={editing} onDone={close} />
        : <RoleTable roles={roles.value} onEdit={setEditing} />}
    </section>
  );
};

export const Route = createFileRoute("/_protected/settings/roles")({
  staticData: { crumb: "Roles" },
  component: Roles,
});
