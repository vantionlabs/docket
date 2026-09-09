import { apiKeysAtom, createApiKeyAtom, revokeApiKeyAtom } from "@/atom/organization-atoms.js";
import { QueryError } from "@/components/app/query-error.js";
import { ApiKeyTable } from "@/components/settings/api-key-table.js";
import { Button } from "@/components/ui/button.js";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog.js";
import { Input } from "@/components/ui/input.js";
import { Label } from "@/components/ui/label.js";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select.js";
import { Skeleton } from "@/components/ui/skeleton.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import type { Role } from "@forge/domain/iam/Permission";
import { createFileRoute } from "@tanstack/react-router";
import { Exit } from "effect";
import { AsyncResult } from "effect/unstable/reactivity";
import { Copy, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

const roles: ReadonlyArray<Role> = ["owner", "admin", "member"];

const ApiKeys = () => {
  const keys = useAtomValue(apiKeysAtom);
  const create = useAtomSet(createApiKeyAtom, { mode: "promiseExit" });
  const creating = useAtomValue(createApiKeyAtom);
  const revoke = useAtomSet(revokeApiKeyAtom);

  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [role, setRole] = React.useState<Role>("member");
  const [secret, setSecret] = React.useState<string | null>(null);

  const onRevoke = React.useCallback((id: string) => {
    revoke(id);
    toast.success("Key revoked");
  }, [revoke]);

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">API keys</h2>
          <p className="text-muted-foreground text-sm">
            For calling the{" "}
            <a href="/api/v1/docs" target="_blank" rel="noreferrer" className="underline">
              public API
            </a>{" "}
            without a browser session. A key acts as the role you give it, not as you.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="size-4" aria-hidden />
          New key
        </Button>
      </div>

      {AsyncResult.isInitial(keys)
        ? <Skeleton className="h-48 w-full" />
        : AsyncResult.isFailure(keys)
        ? <QueryError result={keys} subject="keys" />
        : <ApiKeyTable keys={keys.value} onRevoke={onRevoke} />}

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setName("");
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New API key</DialogTitle>
            <DialogDescription>
              The key is shown once and stored hashed. Give it the least role that does the job.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="key-name">Name</Label>
              <Input
                id="key-name"
                placeholder="CI, Zapier, my laptop"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="key-role">Role</Label>
              <Select value={role} onValueChange={(next) => setRole(next as Role)}>
                <SelectTrigger id="key-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {roles.map((option) => (
                    <SelectItem key={option} value={option}>{option}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-muted-foreground text-xs">
                A key is resolved through the same permission model as a member, so give it the
                narrowest role that does the job.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              disabled={name.trim() === "" || creating.waiting}
              onClick={() => {
                void create({ name: name.trim(), role }).then((exit) => {
                  if (Exit.isFailure(exit)) return toast.error("Could not create that key");

                  setOpen(false);
                  setName("");
                  setSecret(exit.value.secret);
                });
              }}
            >
              Create key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={secret !== null} onOpenChange={(next) => !next && setSecret(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy your key</DialogTitle>
            <DialogDescription>
              Only its hash is stored, so this cannot be shown again. Losing it means creating a new
              one.
            </DialogDescription>
          </DialogHeader>

          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-md bg-muted p-2 font-mono text-xs">
              {secret}
            </code>
            <Button
              variant="outline"
              size="icon"
              aria-label="Copy key"
              onClick={() => {
                if (secret !== null) {
                  void navigator.clipboard.writeText(secret).then(() => toast.success("Copied"));
                }
              }}
            >
              <Copy className="size-4" aria-hidden />
            </Button>
          </div>

          <div className="rounded-md border border-border p-3 text-xs">
            <p className="mb-1 font-medium">Using it</p>
            <pre className="overflow-x-auto text-muted-foreground">
{`curl -H "Authorization: Bearer ${secret ?? ""}" \\
  ${globalThis.location?.origin ?? ""}/api/v1/contacts`}
            </pre>
          </div>

          <DialogFooter>
            <Button onClick={() => setSecret(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
};

export const Route = createFileRoute("/_protected/settings/api-keys")({
  staticData: { crumb: "API keys" },
  component: ApiKeys,
});
