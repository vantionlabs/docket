import { Button } from "@/components/ui/button.js";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog.js";
import { Input } from "@/components/ui/input.js";
import { Label } from "@/components/ui/label.js";
import { Trash2 } from "lucide-react";
import * as React from "react";

/**
 * Deleting an organization.
 *
 * The name must be typed to enable the button. That is not validation theatre:
 * the same string is sent and re-checked server-side, so a request prepared for
 * one organization cannot be replayed against another after switching.
 */
export const DangerZone = (props: {
  readonly organizationName: string;
  readonly isOnlyOrganization: boolean;
  readonly pending: boolean;
  readonly onDelete: (confirmName: string) => void;
}) => {
  const [open, setOpen] = React.useState(false);
  const [typed, setTyped] = React.useState("");

  return (
    <div className="flex flex-col gap-3 rounded-md border border-destructive/40 p-4">
      <div>
        <h3 className="text-sm font-medium text-destructive">Delete this organization</h3>
        <p className="text-muted-foreground mt-1 text-sm">
          Removes every contact, member, role and audit entry belonging to it. This cannot be
          undone.
        </p>
      </div>

      {props.isOnlyOrganization
        ? (
          <p className="text-muted-foreground text-sm">
            This is your only organization. Create another one first — an account with none has no
            way back in.
          </p>
        )
        : (
          <Dialog
            open={open}
            onOpenChange={(next) => {
              setOpen(next);
              if (!next) setTyped("");
            }}
          >
            <DialogTrigger render={<Button variant="destructive" className="self-start" />}>
              <Trash2 className="size-4" aria-hidden />
              Delete organization
            </DialogTrigger>

            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete {props.organizationName}?</DialogTitle>
                <DialogDescription>
                  Everything in this organization goes with it. Type its name to confirm.
                </DialogDescription>
              </DialogHeader>

              <div className="flex flex-col gap-2">
                <Label htmlFor="confirm-name">Organization name</Label>
                <Input
                  id="confirm-name"
                  autoComplete="off"
                  value={typed}
                  placeholder={props.organizationName}
                  onChange={(event) => setTyped(event.target.value)}
                />
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                <Button
                  variant="destructive"
                  disabled={props.pending || typed !== props.organizationName}
                  onClick={() => props.onDelete(typed)}
                >
                  Delete permanently
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
    </div>
  );
};
