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
import type { OrganizationMember } from "@forge/domain/iam/AccessRpc";
import { Users } from "lucide-react";

export const MemberTable = (props: {
  readonly members: ReadonlyArray<OrganizationMember>;
  readonly expanded: string | undefined;
  readonly onToggle: (memberId: string) => void;
}) => {
  if (props.members.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title="No members yet"
        description="Invite people to give them access to this organization."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Email</TableHead>
          <TableHead className="w-32">Role</TableHead>
          <TableHead className="w-32" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {props.members.map((member) => (
          <TableRow key={member.memberId}>
            <TableCell className="font-mono text-sm">{member.email}</TableCell>
            <TableCell>
              <Badge variant="secondary" className="font-mono text-xs">{member.role}</Badge>
            </TableCell>
            <TableCell className="text-right">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => props.onToggle(member.memberId)}
              >
                {props.expanded === member.memberId ? "Close" : "Permissions"}
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
