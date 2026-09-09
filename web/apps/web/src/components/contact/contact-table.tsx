import { EmptyState } from "@/components/app/empty-state.js";
import { Button } from "@/components/ui/button.js";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.js";
import type { Contact, ContactId } from "@forge/domain/contact/ContactRpc";
import { Users } from "lucide-react";

export const ContactTable = (props: {
  readonly contacts: ReadonlyArray<Contact>;
  readonly onDelete: (id: ContactId) => void;
}) => {
  if (props.contacts.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title="No contacts yet"
        description="Contacts are the people this organization keeps track of."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Email</TableHead>
          <TableHead className="w-24" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {props.contacts.map((contact) => (
          <TableRow key={contact.id}>
            <TableCell>{contact.fullName}</TableCell>
            <TableCell className="font-mono text-sm">{contact.email}</TableCell>
            <TableCell className="text-right">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => props.onDelete(contact.id)}
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
