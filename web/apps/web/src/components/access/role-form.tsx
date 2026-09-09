import { setRoleAtom } from "@/atom/access-atoms.js";
import { PermissionPicker } from "@/components/access/permission-picker.js";
import { Button } from "@/components/ui/button.js";
import { Input } from "@/components/ui/input.js";
import { Label } from "@/components/ui/label.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import { CustomRole } from "@forge/domain/iam/AccessRpc";
import type { Permission } from "@forge/domain/iam/Permission";
import * as React from "react";

/** Creates a role, or replaces one when `editing` is supplied. */
export const RoleForm = (props: {
  readonly editing?: CustomRole | undefined;
  readonly onDone: () => void;
}) => {
  const save = useAtomSet(setRoleAtom);
  const result = useAtomValue(setRoleAtom);

  const [name, setName] = React.useState(props.editing?.role ?? "");
  const [selected, setSelected] = React.useState<ReadonlySet<Permission>>(
    new Set(props.editing?.permissions ?? []),
  );

  // Saving invalidates the `roles` key, so the table behind this form re-reads
  // itself; all that is left here is to close the form.
  React.useEffect(() => {
    if (result._tag !== "Success") return;

    props.onDone();
  }, [result, props]);

  const toggle = (permission: Permission, checked: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(permission);
      else next.delete(permission);

      return next;
    });

  return (
    <div className="flex flex-col gap-4 rounded-md border border-border p-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="role-name">Role name</Label>
        <Input
          id="role-name"
          value={name}
          disabled={props.editing !== undefined}
          onChange={(event) => setName(event.target.value)}
          placeholder="editor"
        />
      </div>

      <PermissionPicker selected={selected} onToggle={toggle} />

      <div className="flex gap-2">
        <Button
          type="button"
          disabled={name.trim() === "" || result.waiting}
          onClick={() =>
            save(new CustomRole({ role: name.trim(), permissions: Array.from(selected) }))}
        >
          {props.editing === undefined ? "Create role" : "Save changes"}
        </Button>
        <Button type="button" variant="outline" onClick={props.onDone}>
          Cancel
        </Button>
      </div>
    </div>
  );
};
