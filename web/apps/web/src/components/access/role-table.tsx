import { deleteRoleAtom } from "@/atom/access-atoms.js";
import { EmptyState } from "@/components/app/empty-state.js";
import { Badge } from "@/components/ui/badge.js";
import { Button } from "@/components/ui/button.js";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.js";
import { useAtomSet } from "@effect/atom-react";
import type { CustomRole } from "@forge/domain/iam/AccessRpc";
import { ShieldCheck } from "lucide-react";

export const RoleTable = (props: {
  readonly roles: ReadonlyArray<CustomRole>;
  readonly onEdit: (role: CustomRole) => void;
}) => {
  const remove = useAtomSet(deleteRoleAtom);

  if (props.roles.length === 0) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="No custom roles yet"
        description="Owner, admin and member are always available. Add a role to grant a narrower set of permissions."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Role</TableHead>
          <TableHead>Permissions</TableHead>
          <TableHead className="w-32" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {props.roles.map((role) => (
          <TableRow key={role.role}>
            <TableCell className="font-mono">{role.role}</TableCell>
            <TableCell>
              <div className="flex flex-wrap gap-1">
                {role.permissions.length === 0
                  ? <span className="text-muted-foreground text-sm">none</span>
                  : role.permissions.map((permission) => (
                    <Badge key={permission} variant="secondary" className="font-mono text-xs">
                      {permission}
                    </Badge>
                  ))}
              </div>
            </TableCell>
            <TableCell className="text-right">
              <Button type="button" variant="ghost" size="sm" onClick={() => props.onEdit(role)}>
                Edit
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => remove(role.role)}
              >
                Delete
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
