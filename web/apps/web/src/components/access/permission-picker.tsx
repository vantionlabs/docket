import { Checkbox } from "@/components/ui/checkbox.js";
import { Label } from "@/components/ui/label.js";
import type { Permission } from "@forge/domain/iam/Permission";
import { statements } from "@forge/domain/iam/Permission";
import * as React from "react";

/**
 * Groups the flat permission list back into its resources, so the choices read
 * the way they were declared rather than as one long list of strings.
 */
export const PermissionPicker = (props: {
  readonly selected: ReadonlySet<Permission>;
  readonly onToggle: (permission: Permission, checked: boolean) => void;
  readonly disabled?: boolean;
}) => (
  <div className="grid gap-4 sm:grid-cols-2">
    {Object.entries(statements).map(([resource, actions]) => (
      <div key={resource} className="flex flex-col gap-2">
        <p className="font-mono text-xs text-muted-foreground">{resource}</p>
        {actions.map((action) => {
          const permission = `${resource}:${action}` as Permission;

          return (
            <PermissionCheckbox
              key={permission}
              permission={permission}
              action={action}
              checked={props.selected.has(permission)}
              disabled={props.disabled === true}
              onToggle={props.onToggle}
            />
          );
        })}
      </div>
    ))}
  </div>
);

const PermissionCheckbox = (props: {
  readonly permission: Permission;
  readonly action: string;
  readonly checked: boolean;
  readonly disabled: boolean;
  readonly onToggle: (permission: Permission, checked: boolean) => void;
}) => {
  const id = React.useId();

  return (
    <div className="flex items-center gap-2">
      <Checkbox
        id={id}
        checked={props.checked}
        disabled={props.disabled}
        onCheckedChange={(checked) => props.onToggle(props.permission, checked === true)}
      />
      <Label htmlFor={id} className="text-sm font-normal">{props.action}</Label>
    </div>
  );
};
